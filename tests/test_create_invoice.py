"""Tests for POST /api/v1/invoices — canonical flow B2B-6: Создание накладной.

DoD scenarios (b2b-flows.md#create-invoice):
  - create_invoice_with_moderated_sku_returns_201
  - empty_items_returns_400
  - non_moderated_sku_returns_400
  - others_sku_returns_403
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    TEST_SELLER_ID,
    make_seller_token,
)

TEST_SKU_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TEST_PRODUCT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
OTHER_SELLER_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

VALID_INVOICE_PAYLOAD = {
    "items": [{"sku_id": str(TEST_SKU_ID), "quantity": 10}],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sku_mock(sku_id: uuid.UUID = TEST_SKU_ID, product_id: uuid.UUID = TEST_PRODUCT_ID) -> MagicMock:
    m = MagicMock()
    m.id = sku_id
    m.product_id = product_id
    m.name = "256GB Black"
    return m


def _make_product_mock(seller_id: uuid.UUID = TEST_SELLER_ID, status: str = "MODERATED") -> MagicMock:
    m = MagicMock()
    m.id = TEST_PRODUCT_ID
    m.seller_id = seller_id
    m.status = status
    return m


def _make_invoice_mock(seller_id: uuid.UUID = TEST_SELLER_ID) -> MagicMock:
    item = MagicMock()
    item.id = uuid.uuid4()
    item.sku_id = TEST_SKU_ID
    item.sku_name = "256GB Black"
    item.quantity = 10
    item.accepted_quantity = None

    invoice = MagicMock()
    invoice.id = uuid.uuid4()
    invoice.seller_id = seller_id
    invoice.status = "PENDING"
    invoice.created_at = datetime.now(timezone.utc)
    invoice.updated_at = datetime.now(timezone.utc)
    invoice.accepted_at = None
    invoice.accepted_by = None
    invoice.items = [item]
    return invoice


def _mock_scalars_for_sku(mock_session: MagicMock, skus: list) -> None:
    """Configure mock_session.scalars to return the given SKUs on first call,
    and an empty result (for the post-create re-fetch) on subsequent calls."""
    sku_result = MagicMock()
    sku_result.all.return_value = skus

    mock_session.scalars = AsyncMock(return_value=sku_result)


# ── Happy-path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_invoice_with_moderated_sku_returns_201(client, mock_session):
    """Happy path: MODERATED SKU принадлежит продавцу → 201, status=PENDING."""
    invoice_mock = _make_invoice_mock()

    with patch(
        "app.services.invoice_service.InvoiceService.create",
        new=AsyncMock(return_value=invoice_mock),
    ):
        resp = await client.post(
            "/api/v1/invoices",
            json=VALID_INVOICE_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["seller_id"] == str(TEST_SELLER_ID)
    assert body["accepted_at"] is None
    assert len(body["items"]) == 1
    assert body["items"][0]["sku_name"] == "256GB Black"
    assert body["items"][0]["accepted_quantity"] is None


# ── Unhappy-path ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_items_returns_400(client, mock_session):
    """Пустой список items → 400 INVALID_REQUEST."""
    resp = await client.post(
        "/api/v1/invoices",
        json={"items": []},
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "item" in body["message"].lower()


@pytest.mark.asyncio
async def test_non_moderated_sku_returns_400(client, mock_session):
    """SKU товара в статусе ON_MODERATION (не MODERATED) → 400 INVALID_REQUEST."""
    sku_mock = _make_sku_mock()
    product_mock = _make_product_mock(status="ON_MODERATION")

    _mock_scalars_for_sku(mock_session, [sku_mock])
    mock_session.get = AsyncMock(return_value=product_mock)

    resp = await client.post(
        "/api/v1/invoices",
        json=VALID_INVOICE_PAYLOAD,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "moderated" in body["message"].lower()


@pytest.mark.asyncio
async def test_others_sku_returns_403(client, mock_session):
    """SKU принадлежит другому продавцу → 403 NOT_OWNER."""
    sku_mock = _make_sku_mock()
    product_mock = _make_product_mock(seller_id=OTHER_SELLER_ID, status="MODERATED")

    _mock_scalars_for_sku(mock_session, [sku_mock])
    mock_session.get = AsyncMock(return_value=product_mock)

    resp = await client.post(
        "/api/v1/invoices",
        json=VALID_INVOICE_PAYLOAD,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "NOT_OWNER"
    assert "seller" in body["message"].lower()
