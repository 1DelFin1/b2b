from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, SellerDep, SellerOrServiceKeyDep, get_seller_id
from app.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductPublicResponse,
    ProductShortResponse,
    ProductPaginatedResponse,
)
from app.services.product_service import ProductService

products_router = APIRouter(prefix="/api/v1/products", tags=["products"])


@products_router.get("", response_model=ProductPaginatedResponse)
async def list_products(
    session: SessionDep,
    payload: SellerDep,
    status: Annotated[Literal["CREATED", "ON_MODERATION", "MODERATED", "BLOCKED", "HARD_BLOCKED"] | None, Query()] = None,
    include_deleted: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    seller_id = get_seller_id(payload)
    items, total = await ProductService.get_list(
        session,
        seller_id=seller_id,
        status=status,
        deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    short_items = [
        ProductShortResponse(
            id=row["product"].id,
            title=row["product"].title,
            slug=row["product"].slug,
            status=row["product"].status,
            category_id=row["product"].category_id,
            deleted=row["product"].deleted,
            created_at=row["product"].created_at,
            min_price=row["min_price"],
            cover_image=row["cover_image"],
        )
        for row in items
    ]
    return ProductPaginatedResponse(items=short_items, total_count=total, limit=limit, offset=offset)


@products_router.post("", response_model=ProductResponse, status_code=201)
async def create_product(session: SessionDep, payload: SellerDep, data: ProductCreate):
    seller_id = get_seller_id(payload)
    product = await ProductService.create(session, seller_id=seller_id, data=data)
    return product


@products_router.get("/{product_id}", response_model=None)
async def get_product(product_id: UUID, session: SessionDep, payload: SellerOrServiceKeyDep):
    seller_id = get_seller_id(payload) if payload else None
    product = await ProductService.get_by_id(session, product_id, seller_id=seller_id)
    if payload is None:
        return ProductPublicResponse.model_validate(product)
    return ProductResponse.model_validate(product)


@products_router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    session: SessionDep,
    payload: SellerDep,
    data: ProductUpdate,
):
    seller_id = get_seller_id(payload)
    return await ProductService.update(session, product_id=product_id, seller_id=seller_id, data=data)


@products_router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: UUID, session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    await ProductService.delete(session, product_id=product_id, seller_id=seller_id)
