from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODERATION_EVENTS_PATH = "/api/v1/b2b/events"
B2C_EVENTS_PATH = "/api/v1/b2b/events"


async def _post(url: str, payload: dict, service_key: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers={"X-Service-Key": service_key})
            if resp.status_code >= 400:
                logger.warning("Event POST %s got %d: %s", url, resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Failed to POST event to %s: %s", url, exc)


async def send_product_event_to_moderation(
    session: AsyncSession,
    product_id: UUID,
    seller_id: UUID,
    event: str,  # "CREATED" | "EDITED" | "DELETED"
    product_snapshot: dict | None = None,
    json_before: dict | None = None,
) -> None:
    try:
        from app.core.config import settings
        from app.services.product_service import ProductService
        from app.schemas import ProductResponse

        event_type_map = {
            "CREATED": "PRODUCT_CREATED",
            "EDITED": "PRODUCT_EDITED",
            "DELETED": "PRODUCT_DELETED",
        }
        event_type = event_type_map.get(event, f"PRODUCT_{event}")

        if event == "DELETED":
            inner_payload: dict = {"product_id": str(product_id)}
        else:
            json_after = product_snapshot
            if json_after is None:
                product = await ProductService._load_full(session, product_id)
                if product is not None:
                    raw = ProductResponse.model_validate(product).model_dump(mode="json")
                    for sku in raw.get("skus", []):
                        sku.pop("cost_price", None)
                        sku.pop("reserved_quantity", None)
                    json_after = raw
                else:
                    json_after = {}

            inner_payload = {
                "product_id": str(product_id),
                "seller_id": str(seller_id),
                "category_id": str(json_after.get("category_id", "")) if json_after else "",
                "queue_priority": 3,
                "json_after": json_after,
            }
            if json_before is not None:
                inner_payload["json_before"] = json_before

        payload = {
            "event_type": event_type,
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": inner_payload,
        }

        await _post(
            f"{settings.service.MODERATION_URL}{MODERATION_EVENTS_PATH}",
            payload,
            settings.service.SERVICE_KEY,
        )
    except Exception as exc:
        logger.error("Failed to send product event to moderation: %s", exc)


async def send_product_event_to_b2c(
    event: str,  # "PRODUCT_DELETED" | "PRODUCT_BLOCKED"
    product_id: UUID,
    sku_ids: list[UUID],
) -> None:
    from app.core.config import settings
    payload = {
        "idempotency_key": str(uuid4()),
        "event": event,
        "product_id": str(product_id),
        "sku_ids": [str(s) for s in sku_ids],
        "date": datetime.now(timezone.utc).isoformat(),
    }
    await _post(
        f"{settings.service.B2C_URL}{B2C_EVENTS_PATH}",
        payload,
        settings.service.SERVICE_KEY,
    )


async def send_sku_out_of_stock(sku_ids: list[UUID]) -> None:
    from app.core.config import settings
    payload = {
        "idempotency_key": str(uuid4()),
        "event": "SKU_OUT_OF_STOCK",
        "sku_ids": [str(s) for s in sku_ids],
        "date": datetime.now(timezone.utc).isoformat(),
    }
    await _post(
        f"{settings.service.B2C_URL}{B2C_EVENTS_PATH}",
        payload,
        settings.service.SERVICE_KEY,
    )
