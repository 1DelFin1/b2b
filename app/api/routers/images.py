from uuid import UUID

from fastapi import APIRouter, Form, UploadFile

from app.api.deps import SessionDep, SellerDep, get_seller_id
from app.schemas import ImageAttachRequest, ImageEntityType, ImageUpdateRequest, ImageUploadResponse, ProductImageResponse, SKUImageResponse
from app.services.image_service import ImageService

images_router = APIRouter(prefix="/api/v1", tags=["images"])


@images_router.post("/images", response_model=ImageUploadResponse, status_code=201)
async def upload_image(
    session: SessionDep,
    payload: SellerDep,
    file: UploadFile,
    entity_type: ImageEntityType = Form(...),
    entity_id: UUID | None = Form(default=None),
    ordering: int = Form(default=0),
):
    """Upload an image file. If entity_id is provided, attach it immediately."""
    seller_id = get_seller_id(payload)

    if entity_type == ImageEntityType.PRODUCT and entity_id is not None:
        image = await ImageService.upload_and_attach_product_image(
            session, product_id=entity_id, seller_id=seller_id, file=file, ordering=ordering
        )
        return ImageUploadResponse(id=image.id, url=image.url, ordering=image.ordering, entity_type="PRODUCT", entity_id=entity_id)

    if entity_type == ImageEntityType.SKU and entity_id is not None:
        image = await ImageService.upload_and_attach_sku_image(
            session, sku_id=entity_id, seller_id=seller_id, file=file, ordering=ordering
        )
        return ImageUploadResponse(id=image.id, url=image.url, ordering=image.ordering, entity_type="SKU", entity_id=entity_id)

    # Unattached upload — store in MinIO, return URL without DB record
    url = await ImageService.upload_unattached(seller_id=seller_id, file=file)
    from uuid import uuid4
    return ImageUploadResponse(id=uuid4(), url=url, ordering=ordering, entity_type=entity_type, entity_id=entity_id)


@images_router.post("/products/{product_id}/images", response_model=ProductImageResponse, status_code=201)
async def attach_product_image(
    product_id: UUID,
    session: SessionDep,
    payload: SellerDep,
    data: ImageAttachRequest,
):
    seller_id = get_seller_id(payload)
    image = await ImageService.attach_product_image(
        session, product_id=product_id, seller_id=seller_id, url=data.url, ordering=data.ordering
    )
    return ProductImageResponse(id=image.id, url=image.url, ordering=image.ordering)


@images_router.patch("/products/images/{image_id}", response_model=ProductImageResponse)
async def update_product_image(
    image_id: UUID,
    session: SessionDep,
    payload: SellerDep,
    data: ImageUpdateRequest,
):
    seller_id = get_seller_id(payload)
    image = await ImageService.update_product_image(session, image_id=image_id, seller_id=seller_id, data=data)
    return ProductImageResponse(id=image.id, url=image.url, ordering=image.ordering)


@images_router.delete("/products/images/{image_id}", status_code=204)
async def delete_product_image(image_id: UUID, session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    await ImageService.delete_product_image(session, image_id=image_id, seller_id=seller_id)


@images_router.post("/skus/{sku_id}/images", response_model=SKUImageResponse, status_code=201)
async def attach_sku_image(
    sku_id: UUID,
    session: SessionDep,
    payload: SellerDep,
    data: ImageAttachRequest,
):
    seller_id = get_seller_id(payload)
    image = await ImageService.attach_sku_image(
        session, sku_id=sku_id, seller_id=seller_id, url=data.url, ordering=data.ordering
    )
    return SKUImageResponse(id=image.id, url=image.url, ordering=image.ordering)


@images_router.patch("/skus/images/{image_id}", response_model=SKUImageResponse)
async def update_sku_image(
    image_id: UUID,
    session: SessionDep,
    payload: SellerDep,
    data: ImageUpdateRequest,
):
    seller_id = get_seller_id(payload)
    image = await ImageService.update_sku_image(session, image_id=image_id, seller_id=seller_id, data=data)
    return SKUImageResponse(id=image.id, url=image.url, ordering=image.ordering)


@images_router.delete("/skus/images/{image_id}", status_code=204)
async def delete_sku_image(image_id: UUID, session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    await ImageService.delete_sku_image(session, image_id=image_id, seller_id=seller_id)
