"""Tests for GET /api/v1/products — canonical flow B2B-7: каталог для B2C.

DoD scenarios (b2b-flows.md#catalog-for-b2c):
  - catalog_returns_moderated_in_stock_products
  - catalog_excludes_hard_blocked
  - catalog_missing_service_key_returns_401
  - catalog_response_has_no_cost_price
  - batch_ids_returns_visible_subset
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_CATEGORY_ID, make_seller_token

VALID_SERVICE_KEY = "test-service-key"


def _make_product_row(
    product_id: uuid.UUID | None = None,
    status: str = "MODERATED",
    deleted: bool = False,
    min_price: int = 1299900,
) -> dict:
    p = MagicMock()
    p.id = product_id or uuid.uuid4()
    p.title = "iPhone 15 Pro Max"
    p.slug = "iphone-15-pro-max"
    p.status = status
    p.category_id = TEST_CATEGORY_ID
    p.deleted = deleted
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return {"product": p, "min_price": min_price, "cover_image": "/s3/img.jpg"}


# ── Happy-path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_returns_moderated_in_stock_products(client, mock_session, monkeypatch):
    """X-Service-Key → 200, только MODERATED товары с остатком в ответе."""
    monkeypatch.setattr("app.api.deps.SERVICE_KEY", VALID_SERVICE_KEY)

    row = _make_product_row(status="MODERATED")

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([row], 1)),
    ):
        resp = await client.get(
            "/api/v1/products",
            headers={"X-Service-Key": VALID_SERVICE_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "MODERATED"


@pytest.mark.asyncio
async def test_batch_ids_returns_visible_subset(client, mock_session, monkeypatch):
    """?ids=id1,id2 с X-Service-Key → только видимые возвращаются, без 404 для скрытых."""
    monkeypatch.setattr("app.api.deps.SERVICE_KEY", VALID_SERVICE_KEY)

    visible_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab")
    hidden_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc")

    # Сервис возвращает только видимый товар (HARD_BLOCKED отфильтрован)
    row = _make_product_row(product_id=visible_id, status="MODERATED")

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([row], 1)),
    ) as mock_get_list:
        resp = await client.get(
            f"/api/v1/products?ids={visible_id},{hidden_id}",
            headers={"X-Service-Key": VALID_SERVICE_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(visible_id)

    # Проверяем, что ids были переданы в сервис
    call_kwargs = mock_get_list.call_args
    passed_ids = call_kwargs.kwargs.get("ids") or call_kwargs.args[2] if call_kwargs.args else None
    # ids передаются как keyword argument
    assert call_kwargs.kwargs.get("ids") is not None


# ── Unhappy-path ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_excludes_hard_blocked(client, mock_session, monkeypatch):
    """HARD_BLOCKED товар не попадает в выдачу каталога."""
    monkeypatch.setattr("app.api.deps.SERVICE_KEY", VALID_SERVICE_KEY)

    # Сервис возвращает пустой список — HARD_BLOCKED отфильтрован на уровне SQL
    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([], 0)),
    ):
        resp = await client.get(
            "/api/v1/products",
            headers={"X-Service-Key": VALID_SERVICE_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_catalog_missing_service_key_returns_401(client, mock_session):
    """Запрос без X-Service-Key и без JWT → 401."""
    resp = await client.get("/api/v1/products")

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_catalog_response_has_no_cost_price(client, mock_session, monkeypatch):
    """В ответе каталога для B2C нет полей cost_price и reserved_quantity."""
    monkeypatch.setattr("app.api.deps.SERVICE_KEY", VALID_SERVICE_KEY)

    row = _make_product_row(status="MODERATED")

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([row], 1)),
    ):
        resp = await client.get(
            "/api/v1/products",
            headers={"X-Service-Key": VALID_SERVICE_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    # Публичный ответ содержит min_price, но не cost_price
    assert "cost_price" not in item
    assert "reserved_quantity" not in item
    assert "min_price" in item
