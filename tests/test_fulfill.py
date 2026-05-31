"""Tests for POST /api/v1/inventory/fulfill — canonical flow B2B-10.

DoD scenarios (b2b-flows.md#fulfill-delivery):
  - fulfill_decreases_reserved_quantity
  - active_quantity_unchanged
  - idempotent_fulfill_no_double_deduction
  - missing_service_key_returns_401
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas import InventoryItem, InventoryOrderRequest
from app.services.inventory_service import InventoryService
from tests.conftest import make_mock_session

# ── Constants ─────────────────────────────────────────────────────────────────

SERVICE_KEY = "internal-service-key"

SKU_A_ID = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
SKU_B_ID = uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb")
ORDER_ID = uuid.UUID("cccccccc-3333-3333-3333-cccccccccccc")


def _make_sku(sku_id: uuid.UUID, stock: int, reserved: int) -> MagicMock:
    m = MagicMock()
    m.id = sku_id
    m.stock_quantity = stock
    m.reserved_quantity = reserved
    return m


def _make_reservation(sku_id: uuid.UUID, quantity: int, order_id: uuid.UUID = ORDER_ID) -> MagicMock:
    r = MagicMock()
    r.sku_id = sku_id
    r.order_id = order_id
    r.quantity = quantity
    return r


def _configure_session_for_fulfill(
    session: MagicMock,
    reservations: list,
    skus: list,
) -> None:
    res_result = MagicMock()
    res_result.all.return_value = reservations

    sku_result = MagicMock()
    sku_result.all.return_value = skus

    call_count = 0

    async def scalars_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return res_result if call_count == 1 else sku_result

    session.scalars = AsyncMock(side_effect=scalars_side_effect)
    session.execute = AsyncMock()


def _make_fulfill_request(
    sku_items: list[tuple[uuid.UUID, int]],
    order_id: uuid.UUID = ORDER_ID,
) -> InventoryOrderRequest:
    return InventoryOrderRequest(
        order_id=order_id,
        items=[InventoryItem(sku_id=s, quantity=q) for s, q in sku_items],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fulfill_decreases_reserved_quantity():
    """fulfill_decreases_reserved_quantity: reserved_quantity уменьшился на указанное количество."""
    session = make_mock_session()
    sku_a = _make_sku(SKU_A_ID, stock=10, reserved=3)

    reservation = _make_reservation(SKU_A_ID, quantity=3)
    _configure_session_for_fulfill(session, [reservation], [sku_a])

    request = _make_fulfill_request([(SKU_A_ID, 3)])
    response = await InventoryService.fulfill(session, request)

    assert response.status == "FULFILLED"
    assert response.order_id == ORDER_ID
    # reserved_quantity уменьшилось с 3 до 0
    assert sku_a.reserved_quantity == 0
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_active_quantity_unchanged():
    """active_quantity_unchanged: active_quantity не изменился после fulfill.

    Инвариант: active = stock - reserved. fulfill уменьшает оба на N → active неизменен.
    """
    session = make_mock_session()
    # stock=10, reserved=4, active=6
    sku_a = _make_sku(SKU_A_ID, stock=10, reserved=4)
    active_before = sku_a.stock_quantity - sku_a.reserved_quantity  # 6

    reservation = _make_reservation(SKU_A_ID, quantity=4)
    _configure_session_for_fulfill(session, [reservation], [sku_a])

    request = _make_fulfill_request([(SKU_A_ID, 4)])
    await InventoryService.fulfill(session, request)

    active_after = sku_a.stock_quantity - sku_a.reserved_quantity
    assert active_after == active_before  # active_quantity не изменился
    # Для полноты: оба поля уменьшились на 4
    assert sku_a.reserved_quantity == 0
    assert sku_a.stock_quantity == 6


@pytest.mark.asyncio
async def test_idempotent_fulfill_no_double_deduction():
    """idempotent_fulfill_no_double_deduction: повторный запрос с тем же order_id → 200, данные не изменились.

    После первого fulfill записи резерва удалены. Второй вызов находит пустой
    список резерваций → не меняет ничего → возвращает FULFILLED.
    """
    session = make_mock_session()

    # Второй вызов — нет резерваций в БД
    res_result = MagicMock()
    res_result.all.return_value = []

    sku_result = MagicMock()
    sku_result.all.return_value = []

    call_count = 0

    async def scalars_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return res_result if call_count == 1 else sku_result

    session.scalars = AsyncMock(side_effect=scalars_side_effect)
    session.execute = AsyncMock()

    request = _make_fulfill_request([(SKU_A_ID, 3)])
    response = await InventoryService.fulfill(session, request)

    # Повторный вызов возвращает 200 FULFILLED без ошибок
    assert response.status == "FULFILLED"
    assert response.order_id == ORDER_ID
    # Никакие SKU не были изменены — session.add не вызывался
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_missing_service_key_returns_401(client):
    """missing_service_key_returns_401: вызов без X-Service-Key → 401 UNAUTHORIZED."""
    payload = {
        "order_id": str(ORDER_ID),
        "items": [{"sku_id": str(SKU_A_ID), "quantity": 2}],
    }
    response = await client.post("/api/v1/inventory/fulfill", json=payload)
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
