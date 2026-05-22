from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, ServiceKeyDep
from app.schemas import (
    BatchProductsRequest,
    ProductPublicResponse,
    ProductPublicShortResponse,
    ProductPublicPaginatedResponse,
    SKUPublicResponse,
)
from app.services.product_service import ProductService
from app.services.sku_service import SKUService

public_router = APIRouter(prefix="/api/v1/public", tags=["public-catalog"])


@public_router.get("/products", response_model=ProductPublicPaginatedResponse)
async def list_public_products(
    _: ServiceKeyDep,
    session: SessionDep,
    category_id: UUID | None = None,
    search: str | None = Query(default=None, min_length=3),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    seller_id: UUID | None = None,
    sort: Annotated[Literal["price_asc", "price_desc", "created_desc", "popular"], Query()] = "created_desc",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items, total = await ProductService.get_list(
        session,
        category_id=category_id,
        search=search,
        min_price=min_price,
        max_price=max_price,
        seller_id_filter=seller_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    short_items = [
        ProductPublicShortResponse(
            id=row["product"].id,
            title=row["product"].title,
            slug=row["product"].slug,
            status=row["product"].status,
            category_id=row["product"].category_id,
            min_price=row["min_price"] or 0,
            cover_image=row["cover_image"],
            created_at=row["product"].created_at,
        )
        for row in items
    ]
    return ProductPublicPaginatedResponse(items=short_items, total_count=total, limit=limit, offset=offset)


@public_router.post("/products/batch", response_model=list[ProductPublicResponse])
async def batch_public_products(
    _: ServiceKeyDep,
    session: SessionDep,
    body: BatchProductsRequest,
):
    results = []
    for product_id in body.product_ids:
        try:
            product = await ProductService.get_by_id(session, product_id, public=True)
            results.append(product)
        except Exception:
            continue
    return results


@public_router.get("/products/{product_id}/similar", response_model=list[ProductPublicShortResponse])
async def get_similar_products(
    _: ServiceKeyDep,
    product_id: UUID,
    session: SessionDep,
    limit: int = Query(default=10, ge=1, le=50),
):
    rows = await ProductService.get_similar(session, product_id, limit=limit)
    return [
        ProductPublicShortResponse(
            id=row["product"].id,
            title=row["product"].title,
            slug=row["product"].slug,
            status=row["product"].status,
            category_id=row["product"].category_id,
            min_price=row["min_price"] or 0,
            cover_image=row["cover_image"],
            created_at=row["product"].created_at,
        )
        for row in rows
    ]


@public_router.get("/products/{product_id}", response_model=ProductPublicResponse)
async def get_public_product(_: ServiceKeyDep, product_id: UUID, session: SessionDep):
    return await ProductService.get_by_id(session, product_id, public=True)


@public_router.get("/skus/{sku_id}", response_model=SKUPublicResponse)
async def get_public_sku(_: ServiceKeyDep, sku_id: UUID, session: SessionDep):
    return await SKUService.get_by_id(session, sku_id)
