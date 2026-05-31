from typing import Annotated, AsyncGenerator, Any
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory

SERVICE_KEY = settings.service.SERVICE_KEY


async def get_session() -> AsyncGenerator:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt.JWT_SECRET_KEY,
            algorithms=[settings.jwt.JWT_ALGORITHM],
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid token"},
        )


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("token")


async def get_current_active_auth_seller(request: Request) -> dict[str, Any]:
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required"},
        )

    payload = _decode_token(token)

    if payload.get("account_type") not in ("seller", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Seller access required"},
        )

    return payload


async def get_current_active_auth_admin(request: Request) -> dict[str, Any]:
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required"},
        )

    payload = _decode_token(token)

    if payload.get("account_type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin access required"},
        )

    return payload


async def verify_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if not x_service_key or x_service_key != SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid service key"},
        )


def get_seller_id(payload: dict[str, Any]) -> UUID:
    sub = payload.get("sub") or payload.get("id")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid token payload"},
        )
    return UUID(str(sub))


async def seller_or_service_key(request: Request) -> dict[str, Any] | None:
    """Returns seller JWT payload, or None if valid service key. Raises on auth failure."""
    service_key = request.headers.get("X-Service-Key") or request.headers.get("x-service-key")
    if service_key:
        if service_key != SERVICE_KEY:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid service key"},
            )
        return None  # service key mode: no seller ownership check

    token = _extract_bearer(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required"},
        )

    payload = _decode_token(token)
    if payload.get("account_type") not in ("seller", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Seller access required"},
        )
    return payload


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SellerDep = Annotated[dict[str, Any], Depends(get_current_active_auth_seller)]
AdminDep = Annotated[dict[str, Any], Depends(get_current_active_auth_admin)]
ServiceKeyDep = Annotated[None, Depends(verify_service_key)]
SellerOrServiceKeyDep = Annotated[dict[str, Any] | None, Depends(seller_or_service_key)]
