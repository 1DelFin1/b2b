"""Tests for DELETE /api/v1/skus/{sku_id} — canonical flow B2B-12: Удаление SKU.

Сценарии из b2b-flows.md#delete-sku:
  happy  : delete_sku_succeeds,
           last_sku_on_moderation_transitions_product_to_created
  unhappy: delete_sku_with_active_reserves_returns_409,
           delete_sku_hard_blocked_product_returns_403,
           sku_out_of_stock_event_on_moderated_product
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

SKU_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PRODUCT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_SELLER_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _make_sku(
    stock_quantity: int = 0,
    reserved_quantity: int = 0,
) -> MagicMock:
    m = MagicMock()
    m.id = SKU_ID
    m.product_id = PRODUCT_ID
    m.name = "256GB Black"
    m.price = 12999000
    m.discount = 0
    m.cost_price = 9500000
    m.stock_quantity = stock_quantity
    m.reserved_quantity = reserved_quantity
    m.active_quantity = stock_quantity - reserved_quantity
    m.article = None
    m.images = []
    m.characteristics = []
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _make_product(status: str = "MODERATED", seller_id: uuid.UUID = TEST_SELLER_ID) -> MagicMock:
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


# ── Happy-path tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_sku_succeeds(client, mock_session):
    """Happy path: SKU без резервов удалён, возвращается 204."""
    sku = _make_sku(stock_quantity=0, reserved_quantity=0)
    product = _make_product(status="MODERATED")
    # scalar: первый вызов — get_by_id, второй — count remaining SKUs
    mock_session.scalar = AsyncMock(side_effect=[sku, 1])
    mock_session.get = AsyncMock(return_value=product)

    with patch("app.services.event_service.send_sku_out_of_stock", new=AsyncMock()):
        resp = await client.delete(
            f"/api/v1/skus/{SKU_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_last_sku_on_moderation_transitions_product_to_created(client, mock_session):
    """Последний SKU у товара ON_MODERATION → статус CREATED + событие DELETED в Moderation."""
    sku = _make_sku(stock_quantity=0, reserved_quantity=0)
    product = _make_product(status="ON_MODERATION")
    # После удаления SKU — 0 оставшихся
    mock_session.scalar = AsyncMock(side_effect=[sku, 0])
    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_mod, patch(
        "app.services.event_service.send_sku_out_of_stock", new=AsyncMock()
    ):
        resp = await client.delete(
            f"/api/v1/skus/{SKU_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 204
    assert product.status == "CREATED"
    mock_mod.assert_called_once()
    *_, event_arg = mock_mod.call_args.args
    assert event_arg == "DELETED"


# ── Unhappy-path tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_sku_with_active_reserves_returns_409(client, mock_session):
    """SKU с reserved_quantity > 0 → 409 CONFLICT."""
    sku = _make_sku(stock_quantity=5, reserved_quantity=2)
    product = _make_product(status="MODERATED")
    mock_session.scalar = AsyncMock(return_value=sku)
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.delete(
        f"/api/v1/skus/{SKU_ID}",
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "CONFLICT"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_delete_sku_hard_blocked_product_returns_403(client, mock_session):
    """Попытка удалить SKU у товара HARD_BLOCKED → 403 FORBIDDEN (проверяется первой после IDOR)."""
    sku = _make_sku()
    product = _make_product(status="HARD_BLOCKED")
    mock_session.scalar = AsyncMock(return_value=sku)
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.delete(
        f"/api/v1/skus/{SKU_ID}",
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "FORBIDDEN"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_sku_out_of_stock_event_on_moderated_product(client, mock_session):
    """active_quantity > 0 + товар MODERATED → событие SKU_OUT_OF_STOCK уходит в B2C."""
    sku = _make_sku(stock_quantity=5, reserved_quantity=0)
    product = _make_product(status="MODERATED")
    # SKU не последний — remaining = 1
    mock_session.scalar = AsyncMock(side_effect=[sku, 1])
    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.event_service.send_sku_out_of_stock",
        new=AsyncMock(),
    ) as mock_b2c:
        resp = await client.delete(
            f"/api/v1/skus/{SKU_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 204
    mock_b2c.assert_called_once()
    (sku_ids_arg,) = mock_b2c.call_args.args
    assert SKU_ID in sku_ids_arg