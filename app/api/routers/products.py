from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep, SellerDep, SellerOrServiceKeyDep, get_seller_id
from app.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductDetailResponse,
    ProductPublicResponse,
    ProductPublicPaginatedResponse,
    ProductPublicShortResponse,
    ProductShortResponse,
    ProductPaginatedResponse,
)
from app.services.product_service import ProductService

products_router = APIRouter(prefix="/api/v1/products", tags=["products"])


@products_router.get("", response_model=None)
async def list_products(
    session: SessionDep,
    payload: SellerOrServiceKeyDep,
    # seller-only params
    status: Annotated[Literal["CREATED", "ON_MODERATION", "MODERATED", "BLOCKED", "HARD_BLOCKED"] | None, Query()] = None,
    include_deleted: bool = False,
    # B2C catalog params
    ids: str | None = Query(default=None, description="Comma-separated product UUIDs (B2C batch)"),
    category_id: UUID | None = None,
    search: str | None = Query(default=None, min_length=3),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    seller_id: UUID | None = None,
    sort: Annotated[Literal["price_asc", "price_desc", "created_desc", "popular"], Query()] = "created_desc",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if payload is None:
        # B2C mode: authenticated via X-Service-Key
        ids_list = None
        if ids:
            try:
                ids_list = [UUID(i.strip()) for i in ids.split(",") if i.strip()]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_REQUEST", "message": "Invalid UUID in ids parameter"},
                )

        items, total = await ProductService.get_list(
            session,
            category_id=category_id,
            search=search,
            min_price=min_price,
            max_price=max_price,
            seller_id_filter=seller_id,
            ids=ids_list,
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

    # Seller mode: authenticated via Bearer JWT
    actual_seller_id = get_seller_id(payload)
    items, total = await ProductService.get_list(
        session,
        seller_id=actual_seller_id,
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
    # Service-key callers (Moderation, B2C) get the public view without sensitive fields
    if payload is None:
        return ProductPublicResponse.model_validate(product)
    # Seller cabinet: full view with cost_price, reserved_quantity, blocking_reason, field_reports
    return ProductDetailResponse.model_validate(product)


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
