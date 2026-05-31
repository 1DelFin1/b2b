"""Tests for PATCH /api/v1/products/{id} and PATCH /api/v1/skus/{id}
Canonical flow B2B-3: Редактирование товара/SKU (b2b-flows.md#edit-product).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

PRODUCT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SKU_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OTHER_SELLER_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

VALID_PRODUCT_UPDATE = {
    "title": "iPhone 15 Pro Max (обновлено)",
    "description": "Обновлённое описание",
}

VALID_SKU_UPDATE = {
    "name": "256GB Black Titanium",
    "price": 13499000,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_product(
    status: str = "MODERATED",
    seller_id: uuid.UUID = TEST_SELLER_ID,
) -> MagicMock:
    m = MagicMock()
    m.id = PRODUCT_ID
    m.seller_id = seller_id
    m.category_id = uuid.uuid4()
    m.title = "iPhone 15 Pro Max"
    m.slug = "iphone-15-pro-max"
    m.description = "Флагман Apple"
    m.status = status
    m.deleted = False
    m.blocking_reason_id = None
    m.blocking_reason_title = None
    m.moderator_comment = None
    m.field_reports = []
    m.characteristics = []
    m.images = []
    m.skus = []
    m.rating = 0.0
    m.total_reviews = 0
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _make_sku(
    reserved_quantity: int = 5,
    product_seller_id: uuid.UUID = TEST_SELLER_ID,
) -> MagicMock:
    sku = MagicMock()
    sku.id = SKU_ID
    sku.product_id = PRODUCT_ID
    sku.name = "256GB Black"
    sku.price = 12999000
    sku.cost_price = 9500000
    sku.discount = 0
    sku.stock_quantity = 10
    sku.reserved_quantity = reserved_quantity
    sku.active_quantity = 10 - reserved_quantity
    sku.article = None
    sku.images = []
    sku.characteristics = []
    sku.created_at = datetime.now(timezone.utc)
    sku.updated_at = datetime.now(timezone.utc)

    product = _make_product(status="MODERATED", seller_id=product_seller_id)
    return sku, product


# ── Canonical happy-path tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_moderated_product_returns_to_on_moderation(client, mock_session):
    """MODERATED → ON_MODERATION + событие EDITED при редактировании товара."""
    product = _make_product(status="MODERATED")
    updated_product = _make_product(status="ON_MODERATION")

    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=updated_product),
    ), patch(
        "app.services.product_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        resp = await client.patch(
            f"/api/v1/products/{PRODUCT_ID}",
            json=VALID_PRODUCT_UPDATE,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ON_MODERATION"
    mock_event.assert_called_once()
    *_, event_type = mock_event.call_args.args
    assert event_type == "EDITED"


@pytest.mark.asyncio
async def test_edit_blocked_product_returns_to_on_moderation(client, mock_session):
    """BLOCKED → ON_MODERATION + событие EDITED при редактировании товара."""
    product = _make_product(status="BLOCKED")
    updated_product = _make_product(status="ON_MODERATION")

    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=updated_product),
    ), patch(
        "app.services.product_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        resp = await client.patch(
            f"/api/v1/products/{PRODUCT_ID}",
            json=VALID_PRODUCT_UPDATE,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ON_MODERATION"
    mock_event.assert_called_once()
    *_, event_type = mock_event.call_args.args
    assert event_type == "EDITED"


@pytest.mark.asyncio
async def test_reserves_preserved_after_sku_edit(client, mock_session):
    """reserved_quantity SKU сохраняется после редактирования."""
    sku, product = _make_sku(reserved_quantity=5)
    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.sku_service.SKUService.get_by_id",
        new=AsyncMock(return_value=sku),
    ), patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=product),
    ), patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ):
        # After commit, SKUService re-fetches sku via session.scalar
        mock_session.scalar = AsyncMock(return_value=sku)
        resp = await client.patch(
            f"/api/v1/skus/{SKU_ID}",
            json=VALID_SKU_UPDATE,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reserved_quantity"] == 5


# ── Canonical unhappy-path tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_hard_blocked_returns_403(client, mock_session):
    """Редактирование HARD_BLOCKED товара → 403 FORBIDDEN."""
    product = _make_product(status="HARD_BLOCKED")
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.patch(
        f"/api/v1/products/{PRODUCT_ID}",
        json=VALID_PRODUCT_UPDATE,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "FORBIDDEN"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_edit_others_product_returns_403(client, mock_session):
    """Редактирование чужого товара → 403 NOT_OWNER."""
    product = _make_product(status="MODERATED", seller_id=OTHER_SELLER_ID)
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.patch(
        f"/api/v1/products/{PRODUCT_ID}",
        json=VALID_PRODUCT_UPDATE,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "NOT_OWNER"
    assert "detail" not in body
