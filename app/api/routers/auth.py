from fastapi import APIRouter, status

from app.api.deps import SessionDep
from app.api.utils import Authorization, RefreshTokenService
from app.schemas import SellerCreate, LoginRequest, RefreshRequest, TokenResponse
from app.services.seller_service import SellerService

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@auth_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(session: SessionDep, data: SellerCreate):
    await SellerService.create(session, data)
    return await Authorization.login(session, data.email, data.password)


@auth_router.post("/login", response_model=TokenResponse)
async def login(session: SessionDep, data: LoginRequest):
    return await Authorization.login(session, data.email, data.password)


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(session: SessionDep, data: RefreshRequest):
    return await Authorization.refresh(session, data.refresh_token)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: SessionDep, body: RefreshRequest):
    await RefreshTokenService.revoke(session, body.refresh_token)
