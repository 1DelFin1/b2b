"""Tests for DELETE /api/v1/products/{id} — canonical flow B2B-4: Удаление товара.

Сценарии из b2b-flows.md#delete-product:
  happy : delete_sets_deleted_true, delete_emits_event_to_moderation,
          delete_emits_product_deleted_to_b2c
  unhappy: delete_already_deleted_returns_400, delete_others_product_returns_403,
           deleted_product_not_in_seller_list
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

PRODUCT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
SKU_ID_1 = uuid.UUID("55555555-5555-5555-5555-555555555555")
SKU_ID_2 = uuid.UUID("66666666-6666-6666-6666-666666666666")
OTHER_SELLER_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_product(
    deleted: bool = False,
    seller_id: uuid.UUID = TEST_SELLER_ID,
    status: str = "MODERATED",
) -> MagicMock:
    m = MagicMock()
    m.id = PRODUCT_ID
    m.seller_id = seller_id
    m.category_id = uuid.uuid4()
    m.title = "iPhone 15 Pro Max"
    m.slug = "iphone-15-pro-max"
    m.description = "Флагман Apple"
    m.status = status
    m.deleted = deleted
    m.blocking_reason_id = None
    m.moderator_comment = None
    m.field_reports = []
    m.characteristics = []
    m.images = []
    m.skus = []
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _mock_sku_ids(mock_session: AsyncMock, ids: list[uuid.UUID]) -> None:
    """Configure session.scalars to return given SKU id list."""
    scalars_result = MagicMock()
    scalars_result.all.return_value = ids
    mock_session.scalars = AsyncMock(return_value=scalars_result)


# ── Happy-path tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_sets_deleted_true(client, mock_session):
    """Soft-delete: поле deleted становится True после запроса."""
    product = _make_product(deleted=False)
    mock_session.get = AsyncMock(return_value=product)
    _mock_sku_ids(mock_session, [])

    with patch("app.services.product_service.send_product_event_to_moderation", new=AsyncMock()), \
         patch("app.services.product_service.send_product_event_to_b2c", new=AsyncMock()):
        resp = await client.delete(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 204
    assert product.deleted is True


@pytest.mark.asyncio
async def test_delete_emits_event_to_moderation(client, mock_session):
    """После удаления событие DELETED уходит в Moderation."""
    product = _make_product(deleted=False)
    mock_session.get = AsyncMock(return_value=product)
    _mock_sku_ids(mock_session, [])

    with patch(
        "app.services.product_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_mod, patch(
        "app.services.product_service.send_product_event_to_b2c",
        new=AsyncMock(),
    ):
        resp = await client.delete(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 204
    mock_mod.assert_called_once()
    *_, event_arg = mock_mod.call_args.args
    assert event_arg == "DELETED"


@pytest.mark.asyncio
async def test_delete_emits_product_deleted_to_b2c(client, mock_session):
    """После удаления событие PRODUCT_DELETED уходит в B2C с sku_ids."""
    product = _make_product(deleted=False)
    mock_session.get = AsyncMock(return_value=product)
    _mock_sku_ids(mock_session, [SKU_ID_1, SKU_ID_2])

    with patch(
        "app.services.product_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ), patch(
        "app.services.product_service.send_product_event_to_b2c",
        new=AsyncMock(),
    ) as mock_b2c:
        resp = await client.delete(
            f"/api/v1/products/{PRODUCT_ID}",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 204
    mock_b2c.assert_called_once()
    event_arg, product_id_arg, sku_ids_arg = mock_b2c.call_args.args
    assert event_arg == "PRODUCT_DELETED"
    assert product_id_arg == PRODUCT_ID
    assert set(sku_ids_arg) == {SKU_ID_1, SKU_ID_2}


# ── Unhappy-path tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_already_deleted_returns_400(client, mock_session):
    """Повторное удаление уже удалённого товара → 400 INVALID_REQUEST."""
    product = _make_product(deleted=True)
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.delete(
        f"/api/v1/products/{PRODUCT_ID}",
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "already deleted" in body["message"].lower()
    assert "detail" not in body


@pytest.mark.asyncio
async def test_delete_others_product_returns_403(client, mock_session):
    """Удаление чужого товара → 403 NOT_OWNER."""
    product = _make_product(deleted=False, seller_id=OTHER_SELLER_ID)
    mock_session.get = AsyncMock(return_value=product)

    resp = await client.delete(
        f"/api/v1/products/{PRODUCT_ID}",
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "NOT_OWNER"
    assert "detail" not in body


@pytest.mark.asyncio
async def test_deleted_product_not_in_seller_list(client, mock_session):
    """Удалённый товар не виден в стандартном списке продавца (include_deleted=False)."""
    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([], 0)),
    ) as mock_list:
        resp = await client.get(
            "/api/v1/products",
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total_count"] == 0

    # Убеждаемся, что get_list вызван с deleted=False (значение по умолчанию)
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs.get("deleted", False) is False
