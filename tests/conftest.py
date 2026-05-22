"""Test fixtures for B2B service tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.deps import get_session

# ── JWT helpers ──────────────────────────────────────────────────────────────

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-bytes-long"
TEST_SELLER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_CATEGORY_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def make_seller_token(seller_id: uuid.UUID = TEST_SELLER_ID) -> str:
    payload = {
        "sub": str(seller_id),
        "account_type": "seller",
        "email": "seller@test.com",
        "exp": int(datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()),
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


# ── Session mock ─────────────────────────────────────────────────────────────

def make_mock_session():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture(autouse=True)
def override_jwt_secret(monkeypatch):
    """Use test JWT secret so tokens generated in tests are accepted."""
    monkeypatch.setattr("app.api.deps.settings.jwt.JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setattr("app.api.deps.settings.jwt.JWT_ALGORITHM", "HS256")


@pytest_asyncio.fixture
async def client(mock_session):
    """AsyncClient with overridden DB session."""
    app.dependency_overrides[get_session] = lambda: mock_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Reusable product payload ─────────────────────────────────────────────────

VALID_PRODUCT_PAYLOAD = {
    "title": "iPhone 15 Pro Max",
    "description": "Флагманский смартфон Apple 2024 года с чипом A17 Pro",
    "category_id": str(TEST_CATEGORY_ID),
    "images": [
        {"url": "/s3/iphone15-front.jpg", "ordering": 0},
        {"url": "/s3/iphone15-back.jpg", "ordering": 1},
    ],
    "characteristics": [
        {"name": "Бренд", "value": "Apple"},
        {"name": "Страна-производитель", "value": "Китай"},
    ],
}
