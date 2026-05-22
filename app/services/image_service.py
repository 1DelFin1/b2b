import logging
from uuid import uuid4, UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.images import ProductImageModel, SKUImageModel
from app.models.products import ProductModel
from app.models.skus import SKUModel
from app.schemas import ImageUpdateRequest
from app.services.minio_service import MinioService

logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class ImageService:
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_extension(filename: str, content_type: str) -> str:
        if filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower().strip()
            if ext:
                return ext
        return _CONTENT_TYPE_TO_EXT.get(content_type, "bin")

    @staticmethod
    def _extract_minio_key(url: str, bucket: str) -> str:
        """Extract the object key from a MinIO URL."""
        marker = f"/{bucket}/"
        idx = url.find(marker)
        if idx == -1:
            return url.split("/")[-1]
        return url[idx + len(marker):]

    @staticmethod
    async def _validate_and_read_file(file: UploadFile) -> tuple[bytes, str]:
        """Validate content type and read file bytes. Returns (data, content_type)."""
        content_type = file.content_type or ""
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported image type '{content_type}'. Allowed: jpeg, png, webp",
            )
        data = await file.read()
        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )
        return data, content_type

    @staticmethod
    async def _verify_product_ownership(
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID,
    ) -> ProductModel:
        product = await session.get(ProductModel, product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )
        if product.seller_id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this product",
            )
        return product

    @staticmethod
    async def _verify_sku_ownership(
        session: AsyncSession,
        sku_id: UUID,
        seller_id: UUID,
    ) -> SKUModel:
        sku = await session.get(SKUModel, sku_id)
        if sku is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )
        product = await session.get(ProductModel, sku.product_id)
        if product is None or product.seller_id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this SKU",
            )
        return sku

    # ------------------------------------------------------------------
    # Product image operations
    # ------------------------------------------------------------------

    @classmethod
    async def upload_and_attach_product_image(
        cls,
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID,
        file: UploadFile,
        ordering: int = 0,
    ) -> ProductImageModel:
        await cls._verify_product_ownership(session, product_id, seller_id)

        data, content_type = await cls._validate_and_read_file(file)
        ext = cls._resolve_extension(file.filename or "", content_type)
        key = f"products/{product_id}/{uuid4()}.{ext}"

        minio = MinioService()
        url = minio.upload_file(file_data=data, filename=key, content_type=content_type)

        image = ProductImageModel(
            product_id=product_id,
            url=url,
            ordering=ordering,
            is_main=False,
        )
        session.add(image)
        await session.commit()
        await session.refresh(image)
        return image

    @classmethod
    async def update_product_image(
        cls,
        session: AsyncSession,
        image_id: UUID,
        seller_id: UUID,
        data: ImageUpdateRequest,
    ) -> ProductImageModel:
        image = await session.get(ProductImageModel, image_id)
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found",
            )
        await cls._verify_product_ownership(session, image.product_id, seller_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(image, field, value)

        session.add(image)
        await session.commit()
        await session.refresh(image)
        return image

    @classmethod
    async def delete_product_image(
        cls,
        session: AsyncSession,
        image_id: UUID,
        seller_id: UUID,
    ) -> None:
        image = await session.get(ProductImageModel, image_id)
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found",
            )
        await cls._verify_product_ownership(session, image.product_id, seller_id)

        try:
            from app.core.config import settings
            bucket = settings.minio.MINIO_BUCKET_NAME
            key = cls._extract_minio_key(image.url, bucket)
            MinioService().delete_file(key)
        except Exception:
            logger.warning("Failed to delete product image from MinIO: %s", image.url)

        await session.delete(image)
        await session.commit()

    # ------------------------------------------------------------------
    # SKU image operations
    # ------------------------------------------------------------------

    @classmethod
    async def upload_and_attach_sku_image(
        cls,
        session: AsyncSession,
        sku_id: UUID,
        seller_id: UUID,
        file: UploadFile,
        ordering: int = 0,
    ) -> SKUImageModel:
        await cls._verify_sku_ownership(session, sku_id, seller_id)

        data, content_type = await cls._validate_and_read_file(file)
        ext = cls._resolve_extension(file.filename or "", content_type)
        key = f"skus/{sku_id}/{uuid4()}.{ext}"

        minio = MinioService()
        url = minio.upload_file(file_data=data, filename=key, content_type=content_type)

        image = SKUImageModel(
            sku_id=sku_id,
            url=url,
            ordering=ordering,
        )
        session.add(image)
        await session.commit()
        await session.refresh(image)
        return image

    @classmethod
    async def update_sku_image(
        cls,
        session: AsyncSession,
        image_id: UUID,
        seller_id: UUID,
        data: ImageUpdateRequest,
    ) -> SKUImageModel:
        image = await session.get(SKUImageModel, image_id)
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU image not found",
            )
        await cls._verify_sku_ownership(session, image.sku_id, seller_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(image, field, value)

        session.add(image)
        await session.commit()
        await session.refresh(image)
        return image

    @classmethod
    async def delete_sku_image(
        cls,
        session: AsyncSession,
        image_id: UUID,
        seller_id: UUID,
    ) -> None:
        image = await session.get(SKUImageModel, image_id)
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU image not found",
            )
        await cls._verify_sku_ownership(session, image.sku_id, seller_id)

        try:
            from app.core.config import settings
            bucket = settings.minio.MINIO_BUCKET_NAME
            key = cls._extract_minio_key(image.url, bucket)
            MinioService().delete_file(key)
        except Exception:
            logger.warning("Failed to delete SKU image from MinIO: %s", image.url)

        await session.delete(image)
        await session.commit()

    @classmethod
    async def attach_product_image(
        cls,
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID,
        url: str,
        ordering: int = 0,
    ) -> ProductImageModel:
        await cls._verify_product_ownership(session, product_id, seller_id)
        image = ProductImageModel(
            product_id=product_id,
            url=url,
            ordering=ordering,
            is_main=False,
        )
        session.add(image)
        await session.commit()
        await session.refresh(image)
        return image

    @classmethod
    async def attach_sku_image(
        cls,
        session: AsyncSession,
        sku_id: UUID,
        seller_id: UUID,
        url: str,
        ordering: int = 0,
    ) -> SKUImageModel:
        await cls._verify_sku_ownership(session, sku_id, seller_id)
        image = SKUImageModel(
            sku_id=sku_id,
            url=url,
            ordering=ordering,
        )
        session.add(image)
        await session.commit()
        await session.refresh(image)
        return image

    # ------------------------------------------------------------------
    # Unattached upload (no DB record)
    # ------------------------------------------------------------------

    @classmethod
    async def upload_unattached(cls, seller_id: UUID, file: UploadFile) -> str:
        data, content_type = await cls._validate_and_read_file(file)
        ext = cls._resolve_extension(file.filename or "", content_type)
        key = f"unattached/{seller_id}/{uuid4()}.{ext}"
        return MinioService().upload_file(file_data=data, filename=key, content_type=content_type)
