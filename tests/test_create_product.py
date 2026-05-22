"""Tests for POST /api/v1/products — canonical flow B2B-1: Создание товара."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    VALID_PRODUCT_PAYLOAD,
    TEST_SELLER_ID,
    TEST_CATEGORY_ID,
    make_seller_token,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_product_model(seller_id: uuid.UUID = TEST_SELLER_ID):
    """Return a minimal ProductModel-like object sufficient for ProductResponse."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.seller_id = seller_id
    m.category_id = TEST_CATEGORY_ID
    m.title = VALID_PRODUCT_PAYLOAD["title"]
    m.slug = "iphone-15-pro-max"
    m.description = VALID_PRODUCT_PAYLOAD["description"]
    m.status = "CREATED"
    m.deleted = False
    m.blocking_reason_id = None
    m.blocking_reason_title = None
    m.moderator_comment = None
    m.field_reports = []
    m.characteristics = [
        {"id": str(uuid.uuid4()), "name": "Бренд", "value": "Apple"},
        {"id": str(uuid.uuid4()), "name": "Страна-производитель", "value": "Китай"},
    ]
    m.images = []
    m.skus = []
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


# ── Happy-path tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_product_returns_201_with_created_status(client, mock_session):
    """Happy path: создаём товар — получаем 201 с status=CREATED и пустым skus."""
    product_mock = _make_product_model()

    # category lookup returns a real-ish object (not None)
    mock_category = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_category)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=product_mock),
    ):
        resp = await client.post(
            "/api/v1/products",
            json=VALID_PRODUCT_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "CREATED"
    assert body["skus"] == []
    assert body["deleted"] is False


@pytest.mark.asyncio
async def test_seller_id_taken_from_jwt(client, mock_session):
    """seller_id в ответе берётся из JWT, не из тела запроса."""
    other_seller_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    product_mock = _make_product_model(seller_id=TEST_SELLER_ID)

    mock_category = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_category)

    payload_with_fake_seller = {
        **VALID_PRODUCT_PAYLOAD,
        "seller_id": str(other_seller_id),  # should be ignored
    }

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=product_mock),
    ):
        resp = await client.post(
            "/api/v1/products",
            json=payload_with_fake_seller,
            headers={"Authorization": f"Bearer {make_seller_token(TEST_SELLER_ID)}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["seller_id"] == str(TEST_SELLER_ID)
    assert body["seller_id"] != str(other_seller_id)


# ── Validation / unhappy-path tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_images_returns_400(client, mock_session):
    """Запрос без images (пустой массив) → 400 с кодом INVALID_REQUEST."""
    mock_category = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_category)

    payload = {**VALID_PRODUCT_PAYLOAD, "images": []}
    resp = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )

    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["code"] == "INVALID_REQUEST"
    assert "image" in detail["message"].lower()


@pytest.mark.asyncio
async def test_missing_category_returns_400(client, mock_session):
    """Запрос без category_id → 422 (Pydantic validation), категория обязательна."""
    payload = {k: v for k, v in VALID_PRODUCT_PAYLOAD.items() if k != "category_id"}
    resp = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )
    # Pydantic rejects missing required field with 422
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_category_id_returns_400(client, mock_session):
    """Несуществующий category_id → 400 с кодом INVALID_REQUEST."""
    # category not found → session.get returns None
    mock_session.get = AsyncMock(return_value=None)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=MagicMock()),
    ):
        resp = await client.post(
            "/api/v1/products",
            json=VALID_PRODUCT_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["code"] == "INVALID_REQUEST"
    assert "category" in detail["message"].lower()


@pytest.mark.asyncio
async def test_missing_title_returns_422(client, mock_session):
    """Запрос без title → 422 (Pydantic)."""
    payload = {k: v for k, v in VALID_PRODUCT_PAYLOAD.items() if k != "title"}
    resp = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {make_seller_token()}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client, mock_session):
    """Запрос без токена → 401."""
    resp = await client.post("/api/v1/products", json=VALID_PRODUCT_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_moderation_event_on_creation(client, mock_session):
    """Создание товара без SKU НЕ отправляет событие в модерацию (B2B-1, побочные эффекты)."""
    product_mock = _make_product_model()
    mock_category = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_category)

    with patch(
        "app.services.product_service.ProductService._load_full",
        new=AsyncMock(return_value=product_mock),
    ) as _load, patch(
        "app.services.event_service.send_product_event_to_moderation",
        new=AsyncMock(),
    ) as mock_event:
        resp = await client.post(
            "/api/v1/products",
            json=VALID_PRODUCT_PAYLOAD,
            headers={"Authorization": f"Bearer {make_seller_token()}"},
        )

    assert resp.status_code == 201
    mock_event.assert_not_called()
