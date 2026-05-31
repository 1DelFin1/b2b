"""Tests for GET /api/v1/products (seller mode) — canonical flow B2B-11.

DoD scenarios (b2b-flows.md#list-products):
  - list_returns_only_own_products
  - idor_query_param_seller_id_ignored
  - deleted_products_visible_with_deleted_flag
  - status_filter_works_correctly
  - search_by_title_case_insensitive
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SELLER_ID, make_seller_token

OTHER_SELLER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
PRODUCT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CATEGORY_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_product_row(
    product_id: uuid.UUID = PRODUCT_ID,
    seller_id: uuid.UUID = TEST_SELLER_ID,
    title: str = "iPhone 15 Pro Max",
    status: str = "MODERATED",
    deleted: bool = False,
    skus_count: int = 2,
    total_active_quantity: int = 10,
) -> dict:
    p = MagicMock()
    p.id = product_id
    p.seller_id = seller_id
    p.title = title
    p.slug = title.lower().replace(" ", "-")
    p.status = status
    p.category_id = CATEGORY_ID
    p.deleted = deleted
    p.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "product": p,
        "min_price": 1299900,
        "cover_image": "/s3/img.jpg",
        "skus_count": skus_count,
        "total_active_quantity": total_active_quantity,
    }


def _auth_header(seller_id: uuid.UUID = TEST_SELLER_ID) -> dict:
    return {"Authorization": f"Bearer {make_seller_token(seller_id)}"}


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_returns_only_own_products(client, mock_session):
    """list_returns_only_own_products: ответ содержит только товары текущего продавца."""
    own_row = _make_product_row(seller_id=TEST_SELLER_ID)

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([own_row], 1)),
    ) as mock_get_list:
        resp = await client.get("/api/v1/products", headers=_auth_header())

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(PRODUCT_ID)

    # seller_id в вызове сервиса берётся из JWT, а не из query
    call_kwargs = mock_get_list.call_args.kwargs
    assert call_kwargs["seller_id"] == TEST_SELLER_ID


@pytest.mark.asyncio
async def test_idor_query_param_seller_id_ignored(client, mock_session):
    """idor_query_param_seller_id_ignored: ?seller_id= в query не влияет на выборку — seller_id из JWT."""
    own_row = _make_product_row(seller_id=TEST_SELLER_ID)

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([own_row], 1)),
    ) as mock_get_list:
        # Передаём чужой seller_id в query — должен быть проигнорирован
        resp = await client.get(
            f"/api/v1/products?seller_id={OTHER_SELLER_ID}",
            headers=_auth_header(TEST_SELLER_ID),
        )

    assert resp.status_code == 200

    # Сервис вызван с seller_id из JWT, а не из query param
    call_kwargs = mock_get_list.call_args.kwargs
    assert call_kwargs["seller_id"] == TEST_SELLER_ID
    assert call_kwargs["seller_id"] != OTHER_SELLER_ID


@pytest.mark.asyncio
async def test_deleted_products_visible_with_deleted_flag(client, mock_session):
    """deleted_products_visible_with_deleted_flag: include_deleted=true показывает удалённые товары."""
    deleted_row = _make_product_row(deleted=True)

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([deleted_row], 1)),
    ) as mock_get_list:
        resp = await client.get(
            "/api/v1/products?include_deleted=true",
            headers=_auth_header(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert body["items"][0]["deleted"] is True

    # Флаг deleted=True передан в сервис
    call_kwargs = mock_get_list.call_args.kwargs
    assert call_kwargs["deleted"] is True


@pytest.mark.asyncio
async def test_status_filter_works_correctly(client, mock_session):
    """status_filter_works_correctly: ?status=BLOCKED передаётся в сервис, возвращает только BLOCKED."""
    blocked_row = _make_product_row(status="BLOCKED")

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([blocked_row], 1)),
    ) as mock_get_list:
        resp = await client.get(
            "/api/v1/products?status=BLOCKED",
            headers=_auth_header(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert body["items"][0]["status"] == "BLOCKED"

    # status=BLOCKED передан в сервис
    call_kwargs = mock_get_list.call_args.kwargs
    assert call_kwargs["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_search_by_title_case_insensitive(client, mock_session):
    """search_by_title_case_insensitive: ?search= передаётся в сервис (ilike обеспечивает нечувствительность к регистру)."""
    row = _make_product_row(title="iPhone 15 Pro Max")

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([row], 1)),
    ) as mock_get_list:
        # Верхний регистр — должен найти товар
        resp = await client.get(
            "/api/v1/products?search=IPHONE",
            headers=_auth_header(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert "iphone" in body["items"][0]["title"].lower()

    # search передан в сервис как есть — сервис использует ilike (case-insensitive)
    call_kwargs = mock_get_list.call_args.kwargs
    assert call_kwargs.get("search") == "IPHONE"


# ── Response fields ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_response_includes_skus_count_and_active_quantity(client, mock_session):
    """Ответ включает skus_count и total_active_quantity для каждого товара."""
    row = _make_product_row(skus_count=3, total_active_quantity=25)

    with patch(
        "app.services.product_service.ProductService.get_list",
        new=AsyncMock(return_value=([row], 1)),
    ):
        resp = await client.get("/api/v1/products", headers=_auth_header())

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["skus_count"] == 3
    assert item["total_active_quantity"] == 25
