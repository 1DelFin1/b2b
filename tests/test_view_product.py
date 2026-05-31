"""Tests for GET /api/v1/products/{id} — canonical flow B2B-5: Просмотр карточки.

Сценарии из b2b-flows.md#view-product:
  happy  : get_moderated_product_returns_full_payload,
           get_blocked_product_returns_blocking_reason_and_field_reports
  unhappy: get_others_product_returns_404, get_nonexistent_returns_404
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

PRODUCT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
SKU_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
CATEGORY_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BLOCKING_REASON_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
OTHER_SELLER_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sku_mock(sku_id: uuid.UUID = SKU_ID) -> MagicMock:
    s = MagicMock()
    s.id = sku_id
    s.product_id = PRODUCT_ID
    s.name = "256GB Black"
    s.price = 12999000
    s.cost_price = 9500000
    s.discount = 0
    s.stock_quantity = 12
    s.active_quantity = 10
    s.reserved_quantity = 2
    s.article = None
    s.images = []
    s.characteristics = []
    s.created_at = datetime.now(timezone.utc)
    s.updated_at = datetime.now(timezone.utc)
    return s


def _make_product(
    status: str = "MODERATED",
    seller_id: uuid.UUID = TEST_SELLER_ID,
    blocking_reason_id: uuid.UUID | None = None,
    blocking_reason_title: str | None = None,
    moderator_comment: str | None = None,
    field_reports: list | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = PRODUCT_ID
    m.seller_id = seller_id
    m.category_id = CATEGORY_ID
    m.title = "iPhone 15 Pro Max"
    m.slug = "iphone-15-pro-max"
    m.description = "Флагманский смартфон Apple 2024 года"
    m.status = status
    m.deleted = False
    m.blocked = status in ("BLOCKED", "HARD_BLOCKED")
    m.blocking_reason_id = blocking_reason_id
    m.blocking_reason_title = blocking_reason_title
    m.moderator_comment = moderator_comment
    m.field_reports = field_reports or []
    m.characteristics = []
    m.images = []
    m.skus = [_make_sku_mock()]
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


# ── Happy-path tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_moderated_product_returns_full_payload(client, mock_session):
    """MODERATED товар: полный payload, cost_price у SKU, blocking_reason=null, field_reports=[]."""
    product = _make_product(status="MODERATED")

    with patch(
        "app.services.product_service.ProductService.get_by_id",
        new=AsyncMock(return_value=product),
    ):
        resp = await client.get(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 200
    body = resp.json()

    # Обязательные поля по OpenAPI ProductDetailResponse
    assert body["id"] == str(PRODUCT_ID)
    assert body["seller_id"] == str(TEST_SELLER_ID)
    assert body["category_id"] == str(CATEGORY_ID)
    assert body["status"] == "MODERATED"
    assert body["deleted"] is False
    assert body["blocked"] is False

    # Seller-only: cost_price должен быть в SKU
    assert len(body["skus"]) == 1
    assert body["skus"][0]["cost_price"] == 9500000
    assert body["skus"][0]["reserved_quantity"] == 2

    # При MODERATED blocking_reason null, field_reports пустой
    assert body["blocking_reason"] is None
    assert body["field_reports"] == []


@pytest.mark.asyncio
async def test_get_blocked_product_returns_blocking_reason_and_field_reports(client, mock_session):
    """BLOCKED товар: blocking_reason с title и comment, field_reports с замечаниями."""
    field_reports_data = [
        {"field_name": "description", "sku_id": None, "comment": "Описание не соответствует"},
        {"field_name": "sku_image", "sku_id": str(SKU_ID), "comment": "Фото не соответствует цвету"},
    ]
    product = _make_product(
        status="BLOCKED",
        blocking_reason_id=BLOCKING_REASON_ID,
        blocking_reason_title="Описание не соответствует товару",
        moderator_comment="Несоответствие описания и фотографий",
        field_reports=field_reports_data,
    )

    with patch(
        "app.services.product_service.ProductService.get_by_id",
        new=AsyncMock(return_value=product),
    ):
        resp = await client.get(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "BLOCKED"
    assert body["blocked"] is True

    # blocking_reason — вложенный объект
    br = body["blocking_reason"]
    assert br is not None
    assert br["id"] == str(BLOCKING_REASON_ID)
    assert br["title"] == "Описание не соответствует товару"
    assert br["comment"] == "Несоответствие описания и фотографий"

    # field_reports — список замечаний
    reports = body["field_reports"]
    assert len(reports) == 2
    assert reports[0]["field_name"] == "description"
    assert reports[0]["sku_id"] is None
    assert reports[1]["field_name"] == "sku_image"
    assert reports[1]["sku_id"] == str(SKU_ID)


# ── Unhappy-path tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_others_product_returns_404(client, mock_session):
    """Чужой товар → 404 (не 403 — не раскрываем факт существования)."""
    from fastapi import HTTPException

    with patch(
        "app.services.product_service.ProductService.get_by_id",
        new=AsyncMock(
            side_effect=HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Product not found"},
            )
        ),
    ):
        resp = await client.get(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_get_nonexistent_returns_404(client, mock_session):
    """Несуществующий product_id → 404."""
    from fastapi import HTTPException

    with patch(
        "app.services.product_service.ProductService.get_by_id",
        new=AsyncMock(
            side_effect=HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Product not found"},
            )
        ),
    ):
        nonexistent = uuid.uuid4()
        resp = await client.get(
            f"/api/v1/products/{nonexistent}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_service_key_gets_public_view_without_sensitive_fields(client, mock_session):
    """X-Service-Key вызов → ProductPublicResponse без cost_price и reserved_quantity."""
    from app.core.config import settings

    product = _make_product(status="MODERATED")

    with patch(
        "app.services.product_service.ProductService.get_by_id",
        new=AsyncMock(return_value=product),
    ):
        resp = await client.get(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"X-Service-Key": settings.service.SERVICE_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    # Public view: cost_price и reserved_quantity не должны присутствовать в SKU
    if body.get("skus"):
        for sku in body["skus"]:
            assert "cost_price" not in sku
            assert "reserved_quantity" not in sku
