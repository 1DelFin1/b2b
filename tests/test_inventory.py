"""Tests for POST /api/v1/inventory/reserve and /unreserve — canonical flow B2B-8.

DoD scenarios (b2b-flows.md#reserve-sku):
  - reserve_all_skus_succeeds
  - partial_insufficient_stock_returns_409_all_rollback
  - idempotent_reserve_returns_200_without_double_deduction
  - sku_out_of_stock_event_emitted
  - unreserve_restores_quantities
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import InventoryItem, InventoryOrderRequest, ReserveRequest
from app.services.inventory_service import InventoryService
from tests.conftest import make_mock_session

# ── Fixtures ─────────────────────────────────────────────────────────────────

SERVICE_KEY = "internal-service-key"

SKU_A_ID = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
SKU_B_ID = uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb")
ORDER_ID = uuid.UUID("cccccccc-3333-3333-3333-cccccccccccc")
IDEM_KEY = uuid.UUID("dddddddd-4444-4444-4444-dddddddddddd")


def _make_sku(sku_id: uuid.UUID, stock: int, reserved: int) -> MagicMock:
    m = MagicMock()
    m.id = sku_id
    m.stock_quantity = stock
    m.reserved_quantity = reserved
    m.active_quantity = stock - reserved  # mirrors the model property
    return m


def _make_reserve_request(
    sku_items: list[tuple[uuid.UUID, int]],
    idempotency_key: uuid.UUID = IDEM_KEY,
    order_id: uuid.UUID = ORDER_ID,
) -> ReserveRequest:
    return ReserveRequest(
        idempotency_key=idempotency_key,
        order_id=order_id,
        items=[InventoryItem(sku_id=s, quantity=q) for s, q in sku_items],
    )


def _make_unreserve_request(
    sku_items: list[tuple[uuid.UUID, int]],
    order_id: uuid.UUID = ORDER_ID,
) -> InventoryOrderRequest:
    return InventoryOrderRequest(
        order_id=order_id,
        items=[InventoryItem(sku_id=s, quantity=q) for s, q in sku_items],
    )


def _configure_session_for_reserve(
    session: MagicMock,
    skus: list,
    idempotency_exists: bool = False,
) -> None:
    """Set up mock session.scalars to handle idempotency check then SKU lock."""
    idempotency_result = MagicMock()
    idempotency_result.first.return_value = MagicMock() if idempotency_exists else None

    sku_result = MagicMock()
    sku_result.all.return_value = skus

    call_count = 0

    async def scalars_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return idempotency_result
        return sku_result

    session.scalars = AsyncMock(side_effect=scalars_side_effect)


def _configure_session_for_unreserve(session: MagicMock, reservations: list, skus: list) -> None:
    """Set up mock session.scalars for unreserve: first reservations, then SKUs."""
    res_result = MagicMock()
    res_result.all.return_value = reservations

    sku_result = MagicMock()
    sku_result.all.return_value = skus

    call_count = 0

    async def scalars_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return res_result
        return sku_result

    session.scalars = AsyncMock(side_effect=scalars_side_effect)
    session.execute = AsyncMock()


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reserve_all_skus_succeeds():
    """Happy path: both SKUs have enough stock → 200 RESERVED, quantities updated."""
    session = make_mock_session()
    sku_a = _make_sku(SKU_A_ID, stock=10, reserved=2)  # active=8
    sku_b = _make_sku(SKU_B_ID, stock=5, reserved=0)   # active=5
    _configure_session_for_reserve(session, [sku_a, sku_b])

    request = _make_reserve_request([(SKU_A_ID, 3), (SKU_B_ID, 2)])

    with patch("app.services.event_service.send_sku_out_of_stock", new=AsyncMock()):
        response = await InventoryService.reserve(session, request)

    assert response.status == "RESERVED"
    assert response.order_id == ORDER_ID

    # active_quantity must decrease: reserved_quantity increases
    assert sku_a.reserved_quantity == 5   # was 2, +3
    assert sku_b.reserved_quantity == 2   # was 0, +2

    # active_quantity = stock - reserved
    assert sku_a.stock_quantity - sku_a.reserved_quantity == 5   # 10-5
    assert sku_b.stock_quantity - sku_b.reserved_quantity == 3   # 5-2

    session.commit.assert_called_once()


# ── Unhappy path ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_insufficient_stock_returns_409_all_rollback():
    """One SKU lacks sufficient stock → 409, no SKU is modified (all-or-nothing)."""
    from fastapi import HTTPException

    session = make_mock_session()
    sku_a = _make_sku(SKU_A_ID, stock=10, reserved=0)  # active=10, enough
    sku_b = _make_sku(SKU_B_ID, stock=3, reserved=0)   # active=3, insufficient for 5
    _configure_session_for_reserve(session, [sku_a, sku_b])

    reserved_a_before = sku_a.reserved_quantity
    reserved_b_before = sku_b.reserved_quantity

    request = _make_reserve_request([(SKU_A_ID, 2), (SKU_B_ID, 5)])

    with pytest.raises(HTTPException) as exc_info:
        await InventoryService.reserve(session, request)

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail["code"] == "INSUFFICIENT_STOCK"
    failed = detail["failed_items"]
    assert len(failed) == 1
    assert failed[0]["sku_id"] == str(SKU_B_ID)
    assert failed[0]["reason"] == "INSUFFICIENT_STOCK"

    # All-or-nothing: neither SKU was modified
    assert sku_a.reserved_quantity == reserved_a_before
    assert sku_b.reserved_quantity == reserved_b_before
    session.commit.assert_not_called()


# ── Idempotency ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_idempotent_reserve_returns_200_without_double_deduction():
    """Repeated request with same idempotency_key → 200 without re-reserving."""
    session = make_mock_session()
    sku_a = _make_sku(SKU_A_ID, stock=10, reserved=3)
    # idempotency_exists=True means first scalars call returns a non-None record
    _configure_session_for_reserve(session, [sku_a], idempotency_exists=True)

    request = _make_reserve_request([(SKU_A_ID, 3)])

    response = await InventoryService.reserve(session, request)

    assert response.status == "RESERVED"
    assert response.order_id == ORDER_ID

    # SKU quantities must not change — no second deduction
    assert sku_a.reserved_quantity == 3
    session.commit.assert_not_called()


# ── Out-of-stock event ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sku_out_of_stock_event_emitted():
    """After reserve active_quantity reaches 0 → SKU_OUT_OF_STOCK event sent to B2C."""
    session = make_mock_session()
    # SKU has exactly 5 active units; we reserve all 5 → active becomes 0
    sku_a = _make_sku(SKU_A_ID, stock=5, reserved=0)
    _configure_session_for_reserve(session, [sku_a])

    request = _make_reserve_request([(SKU_A_ID, 5)])

    with patch(
        "app.services.event_service.send_sku_out_of_stock",
        new=AsyncMock(),
    ) as mock_event:
        await InventoryService.reserve(session, request)

    mock_event.assert_called_once()
    called_sku_ids = mock_event.call_args[0][0]
    assert SKU_A_ID in called_sku_ids


# ── Unreserve ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unreserve_restores_quantities():
    """Unreserve correctly increases active_quantity and decreases reserved_quantity."""
    session = make_mock_session()

    # Simulate reservation record in DB
    reservation = MagicMock()
    reservation.sku_id = SKU_A_ID
    reservation.order_id = ORDER_ID
    reservation.quantity = 3

    # SKU currently has 3 reserved
    sku_a = _make_sku(SKU_A_ID, stock=10, reserved=3)

    _configure_session_for_unreserve(session, [reservation], [sku_a])

    request = _make_unreserve_request([(SKU_A_ID, 3)])
    response = await InventoryService.unreserve(session, request)

    assert response.status == "UNRESERVED"
    assert response.order_id == ORDER_ID

    # reserved_quantity must decrease back to 0
    assert sku_a.reserved_quantity == 0
    # active_quantity restored: stock - reserved = 10 - 0 = 10
    assert sku_a.stock_quantity - sku_a.reserved_quantity == 10

    session.commit.assert_called_once()
