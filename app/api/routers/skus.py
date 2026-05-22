from uuid import UUID

from fastapi import APIRouter

from app.api.deps import SessionDep, SellerDep, get_seller_id
from app.schemas import SKUCreate, SKUUpdate, SKUResponse
from app.services.sku_service import SKUService

skus_router = APIRouter(prefix="/api/v1/skus", tags=["skus"])
product_skus_router = APIRouter(prefix="/api/v1/products", tags=["skus"])


@product_skus_router.get("/{product_id}/skus", response_model=list[SKUResponse])
async def list_product_skus(product_id: UUID, session: SessionDep, seller: SellerDep):
    return await SKUService.get_by_product(session, product_id)


@skus_router.post("", response_model=SKUResponse, status_code=201)
async def create_sku(session: SessionDep, payload: SellerDep, data: SKUCreate):
    seller_id = get_seller_id(payload)
    return await SKUService.create(session, data=data, seller_id=seller_id)


@skus_router.get("/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: UUID, session: SessionDep, seller: SellerDep):
    return await SKUService.get_by_id(session, sku_id)


@skus_router.patch("/{sku_id}", response_model=SKUResponse)
async def update_sku(sku_id: UUID, session: SessionDep, payload: SellerDep, data: SKUUpdate):
    seller_id = get_seller_id(payload)
    return await SKUService.update(session, sku_id=sku_id, data=data, seller_id=seller_id)


@skus_router.delete("/{sku_id}", status_code=204)
async def delete_sku(sku_id: UUID, session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    await SKUService.delete(session, sku_id=sku_id, seller_id=seller_id)
