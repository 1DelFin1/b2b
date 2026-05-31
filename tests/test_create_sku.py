"""Tests for POST /api/v1/skus — canonical flow B2B-2: Создание SKU."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

PRODUCT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

VALID_SKU_PAYLOAD: dict = {
    "product_id": str(PRODUCT_ID),
    "name": "256GB Black",
    "price": 12999000,
    "cost_price": 9500000,
    "discount": 0,
    "images": [{"url": "/s3/iphone15-black-256.jpg", "ordering": 0}],
    "characteristics": [
        {"name": "Цвет", "value": "Чёрный"},
        {"name": "Объём памяти", "value": "256 ГБ"},
    ],
}


def _make_product(status: str = "CREATED", seller_id: uuid.UUID = TEST_SELLER_ID) -> MagicMock:
    m = MagicMock()
    m.id = PRODUCT_ID
    m.seller_id = seller_id
    m.category_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    m.title = "iPhone 15 Pro Max"
    m.slug = "iphone-15-pro-max"
    m.description = "Флагман Apple"
    m.status = status
    m.deleted = False
    m.blocking_reason_id = None
    m.moderator_comment = None
    m.field_reports = []
    m.characteristics = []
    m.images = []
    m.skus = []
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _make_sku() -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.product_id = PRODUCT_ID
    m.name = VALID_SKU_PAYLOAD["name"]
    m.price = VALID_SKU_PAYLOAD["price"]
    m.cost_price = VALID_SKU_PAYLOAD["cost_price"]
    m.discount = 0
    m.stock_quantity = 0
    m.reserved_quantity = 0
    m.active_quantity = 0
    m.article = None
    m.images = []
    m.characteristics = []
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


# ── DoD tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_sku_transitions_product_to_on_moderation(client, mock_session):
    """Первый SKU: статус товара CREATED → ON_MODERATION."""
    product = _make_product(status="CREATED")
    mock_session.get = AsyncMock(return_value=product)
    mock_session.scalar = AsyncMock(return_value=_make_sku())

    with patch("app.services.event_service.send_product_event_to_moderation", new=AsyncMock()):
        resp = await client.post(
            "/api/v1/skus",
            json=VALID_SKU_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    assert product.status == "ON_MODERATION"


@pytest.mark.asyncio
async def test_first_sku_emits_created_event_to_moderation(client, mock_session):
    """Первый SKU: событие CREATED уходит в Moderation с product_id и seller_id."""
    product = _make_product(status="CREATED")
    mock_session.get = AsyncMock(return_value=product)
    mock_session.scalar = AsyncMock(return_value=_make_sku())

    with patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        resp = await client.post(
            "/api/v1/skus",
            json=VALID_SKU_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    mock_event.assert_called_once()
    _, called_product_id, called_seller_id, called_event = mock_event.call_args.args
    assert called_product_id == PRODUCT_ID
    assert called_seller_id == TEST_SELLER_ID
    assert called_event == "CREATED"


@pytest.mark.asyncio
async def test_second_sku_no_state_change(client, mock_session):
    """Второй SKU: статус ON_MODERATION не меняется, событие не отправляется."""
    product = _make_product(status="ON_MODERATION")
    mock_session.get = AsyncMock(return_value=product)
    mock_session.scalar = AsyncMock(return_value=_make_sku())

    with patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        resp = await client.post(
            "/api/v1/skus",
            json=VALID_SKU_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    assert product.status == "ON_MODERATION"
    mock_event.assert_not_called()


@pytest.mark.asyncio
async def test_add_sku_to_hard_blocked_returns_403(client, mock_session):
    """Попытка добавить SKU к HARD_BLOCKED товару → 403 FORBIDDEN."""
    product = _make_product(status="HARD_BLOCKED")
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.post(
        "/api/v1/skus",
        json=VALID_SKU_PAYLOAD,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "FORBIDDEN"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_missing_image_returns_400(client, mock_session):
    """Запрос без изображения → 400 INVALID_REQUEST."""
    product = _make_product(status="CREATED")
    mock_session.get = AsyncMock(return_value=product)

    payload = {**VALID_SKU_PAYLOAD, "images": []}
    resp = await client.post(
        "/api/v1/skus",
        json=payload,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "image" in body["message"].lower()
    assert "detail" not in body


@pytest.mark.asyncio
async def test_product_not_found_returns_404(client, mock_session):
    """Несуществующий product_id → 404 NOT_FOUND."""
    mock_session.get = AsyncMock(return_value=None)

    resp = await client.post(
        "/api/v1/skus",
        json=VALID_SKU_PAYLOAD,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client, mock_session):
    """Запрос без токена → 401 UNAUTHORIZED."""
    resp = await client.post("/api/v1/skus", json=VALID_SKU_PAYLOAD)

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"
    assert "detail" not in body


# ── B2B-2 rule from 2026-05-27: add SKU to MODERATED/BLOCKED → re-moderation ─

@pytest.mark.asyncio
async def test_add_sku_to_moderated_product_transitions_to_on_moderation(client, mock_session):
    """Добавление SKU к MODERATED товару → ON_MODERATION + событие EDITED (правило с 2026-05-27)."""
    product = _make_product(status="MODERATED")
    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=product),
    ), patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        mock_session.scalar = AsyncMock(return_value=_make_sku())
        resp = await client.post(
            "/api/v1/skus",
            json=VALID_SKU_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    assert product.status == "ON_MODERATION"
    mock_event.assert_called_once()
    *_, event_type = mock_event.call_args.args
    assert event_type == "EDITED"


@pytest.mark.asyncio
async def test_add_sku_to_blocked_product_transitions_to_on_moderation(client, mock_session):
    """Добавление SKU к BLOCKED товару → ON_MODERATION + событие EDITED (правило с 2026-05-27)."""
    product = _make_product(status="BLOCKED")
    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=product),
    ), patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        mock_session.scalar = AsyncMock(return_value=_make_sku())
        resp = await client.post(
            "/api/v1/skus",
            json=VALID_SKU_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    assert product.status == "ON_MODERATION"
    mock_event.assert_called_once()
    *_, event_type = mock_event.call_args.args
    assert event_type == "EDITED"


@pytest.mark.asyncio
async def test_add_sku_to_on_moderation_no_event(client, mock_session):
    """Добавление SKU к товару в ON_MODERATION — статус не меняется, событие не отправляется."""
    product = _make_product(status="ON_MODERATION")
    mock_session.get = AsyncMock(return_value=product)
    mock_session.scalar = AsyncMock(return_value=_make_sku())

    with patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        resp = await client.post(
            "/api/v1/skus",
            json=VALID_SKU_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    assert product.status == "ON_MODERATION"
    mock_event.assert_not_called()
