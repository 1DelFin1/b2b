"""Tests for POST /api/v1/moderation/events — canonical flow B2B-9.

DoD scenarios (b2b-flows.md#apply-moderation):
  - moderated_event_clears_blocking_data
  - blocked_soft_saves_field_reports
  - blocked_hard_sets_terminal_status
  - hard_blocked_product_rejects_seller_edits
  - duplicate_event_same_idempotency_key_no_side_effects
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

SERVICE_KEY = "internal-service-key"

PRODUCT_ID = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
IDEM_KEY = uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb")
BLOCKING_REASON_ID = uuid.UUID("cccccccc-3333-3333-3333-cccccccccccc")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_product_mock(
    status: str = "ON_MODERATION",
    last_idem_key: str | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = PRODUCT_ID
    m.seller_id = TEST_SELLER_ID
    m.status = status
    m.deleted = False
    m.blocking_reason_id = None
    m.blocking_reason_title = None
    m.moderator_comment = None
    m.field_reports = []
    m.last_moderation_idempotency_key = last_idem_key
    return m


def _moderation_payload(
    event_type: str = "MODERATED",
    hard_block: bool = False,
    field_reports: list | None = None,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "idempotency_key": idempotency_key or str(IDEM_KEY),
        "product_id": str(PRODUCT_ID),
        "event_type": event_type,
        "hard_block": hard_block,
        "blocking_reason_id": str(BLOCKING_REASON_ID) if event_type == "BLOCKED" else None,
        "moderator_comment": "Test comment" if event_type == "BLOCKED" else None,
        "field_reports": field_reports or [],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_moderated_event_clears_blocking_data(client, mock_session):
    """MODERATED event → status=MODERATED, blocking_reason and field_reports cleared."""
    product = _make_product_mock(
        status="ON_MODERATION",
        last_idem_key=None,
    )
    # Previously had blocking data
    product.blocking_reason_id = BLOCKING_REASON_ID
    product.field_reports = [{"field_name": "title", "comment": "Bad title"}]
    mock_session.get = AsyncMock(return_value=product)

    with patch("app.services.product_service.send_product_event_to_b2c", new=AsyncMock()):
        resp = await client.post(
            "/api/v1/moderation/events",
            json=_moderation_payload("MODERATED"),
            headers={"X-Service-Key": SERVICE_KEY},
        )

    assert resp.status_code == 204

    assert product.status == "MODERATED"
    assert product.blocking_reason_id is None
    assert product.blocking_reason_title is None
    assert product.moderator_comment is None
    assert product.field_reports == []
    assert product.last_moderation_idempotency_key == str(IDEM_KEY)
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_blocked_soft_saves_field_reports(client, mock_session):
    """BLOCKED + hard_block=false → status=BLOCKED, field_reports saved, cascade to B2C."""
    product = _make_product_mock(status="ON_MODERATION")
    mock_session.get = AsyncMock(return_value=product)

    sku_ids_result = MagicMock()
    sku_ids_result.all.return_value = [uuid.uuid4()]
    mock_session.scalars = AsyncMock(return_value=sku_ids_result)

    field_reports = [
        {"field_name": "description", "sku_id": None, "comment": "Misleading text"},
        {"field_name": "sku_image", "sku_id": str(uuid.uuid4()), "comment": "Wrong photo"},
    ]

    with patch(
        "app.services.product_service.send_product_event_to_b2c", new=AsyncMock()
    ) as mock_b2c:
        resp = await client.post(
            "/api/v1/moderation/events",
            json=_moderation_payload("BLOCKED", hard_block=False, field_reports=field_reports),
            headers={"X-Service-Key": SERVICE_KEY},
        )

    assert resp.status_code == 204

    assert product.status == "BLOCKED"
    assert product.blocking_reason_id == BLOCKING_REASON_ID
    assert len(product.field_reports) == 2
    assert product.last_moderation_idempotency_key == str(IDEM_KEY)

    mock_b2c.assert_called_once()
    call_args = mock_b2c.call_args[0]
    assert call_args[0] == "PRODUCT_BLOCKED"
    assert call_args[1] == PRODUCT_ID


@pytest.mark.asyncio
async def test_blocked_hard_sets_terminal_status(client, mock_session):
    """BLOCKED + hard_block=true → status=HARD_BLOCKED, cascade to B2C."""
    product = _make_product_mock(status="ON_MODERATION")
    mock_session.get = AsyncMock(return_value=product)

    sku_ids_result = MagicMock()
    sku_ids_result.all.return_value = [uuid.uuid4()]
    mock_session.scalars = AsyncMock(return_value=sku_ids_result)

    with patch(
        "app.services.product_service.send_product_event_to_b2c", new=AsyncMock()
    ) as mock_b2c:
        resp = await client.post(
            "/api/v1/moderation/events",
            json=_moderation_payload("BLOCKED", hard_block=True),
            headers={"X-Service-Key": SERVICE_KEY},
        )

    assert resp.status_code == 204
    assert product.status == "HARD_BLOCKED"
    mock_b2c.assert_called_once()
    assert mock_b2c.call_args[0][0] == "PRODUCT_BLOCKED"
    assert mock_b2c.call_args[0][1] == PRODUCT_ID


# ── HARD_BLOCKED rejects seller actions ───────────────────────────────────────

@pytest.mark.asyncio
async def test_hard_blocked_product_rejects_seller_edits(client, mock_session):
    """PUT and DELETE on HARD_BLOCKED product → 403 FORBIDDEN."""
    product = _make_product_mock(status="HARD_BLOCKED")
    mock_session.get = AsyncMock(return_value=product)

    token = make_seller_token()

    # PUT should be blocked
    resp_put = await client.patch(
        f"/api/v1/products/{PRODUCT_ID}",
        json={"title": "New title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_put.status_code == 403
    assert resp_put.json()["code"] == "FORBIDDEN"

    # DELETE should also be blocked
    mock_session.get = AsyncMock(return_value=product)
    resp_delete = await client.delete(
        f"/api/v1/products/{PRODUCT_ID}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_delete.status_code == 403
    assert resp_delete.json()["code"] == "FORBIDDEN"


# ── Idempotency ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_event_same_idempotency_key_no_side_effects(client, mock_session):
    """Repeated event with same idempotency_key → 204 without any changes."""
    product = _make_product_mock(
        status="MODERATED",
        last_idem_key=str(IDEM_KEY),  # already processed
    )
    mock_session.get = AsyncMock(return_value=product)

    with patch(
        "app.services.product_service.send_product_event_to_b2c", new=AsyncMock()
    ) as mock_b2c:
        resp = await client.post(
            "/api/v1/moderation/events",
            json=_moderation_payload("MODERATED"),
            headers={"X-Service-Key": SERVICE_KEY},
        )

    assert resp.status_code == 204

    # No commit — nothing was changed
    mock_session.commit.assert_not_called()
    # No B2C event sent
    mock_b2c.assert_not_called()
    # Status unchanged
    assert product.status == "MODERATED"


# ── Auth ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_service_key_returns_401(client, mock_session):
    """Request without X-Service-Key → 401."""
    resp = await client.post(
        "/api/v1/moderation/events",
        json=_moderation_payload("MODERATED"),
        # No X-Service-Key header
    )
    assert resp.status_code == 401
