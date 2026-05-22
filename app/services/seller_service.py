import logging
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.exceptions import SELLER_NOT_FOUND, SELLER_ALREADY_EXISTS
from app.models.sellers import SellerModel
from app.schemas import SellerCreate, SellerUpdate

logger = logging.getLogger(__name__)


class SellerService:
    @classmethod
    async def get_by_id(cls, session: AsyncSession, seller_id: UUID) -> SellerModel | None:
        stmt = select(SellerModel).where(SellerModel.id == seller_id)
        return await session.scalar(stmt)

    @classmethod
    async def get_by_email(cls, session: AsyncSession, email: str) -> SellerModel | None:
        stmt = select(SellerModel).where(SellerModel.email == email)
        return await session.scalar(stmt)

    @classmethod
    async def get_seller_by_id(
        cls,
        session: AsyncSession,
        seller_id: UUID,
        sync_metrics: bool = False,
    ) -> SellerModel | None:
        seller = await cls.get_by_id(session, seller_id)
        if seller is None:
            return None
        if sync_metrics:
            seller = await cls.sync_metrics(session, seller)
        return seller

    @classmethod
    async def sync_metrics(cls, session: AsyncSession, seller: SellerModel) -> SellerModel:
        """Compute seller rating from local products DB."""
        from app.models.products import ProductModel
        avg_rating = await session.scalar(
            select(func.avg(ProductModel.rating)).where(
                ProductModel.seller_id == seller.id,
                ProductModel.deleted.is_(False),
                ProductModel.rating > 0,
            )
        )

        next_rating = round(float(avg_rating), 2) if avg_rating is not None else 0.0
        rating_changed = abs((seller.rating or 0.0) - next_rating) > 1e-9

        if rating_changed:
            seller.rating = next_rating
            session.add(seller)
            await session.commit()
            await session.refresh(seller)

        return seller

    @classmethod
    async def create(cls, session: AsyncSession, data: SellerCreate) -> SellerModel:
        existing = await cls.get_by_email(session, data.email)
        if existing is not None:
            raise SELLER_ALREADY_EXISTS

        dump = data.model_dump(exclude={"password"})
        dump["hashed_password"] = get_password_hash(data.password)
        seller = SellerModel(**dump)
        session.add(seller)
        await session.commit()
        await session.refresh(seller)
        return seller

    @classmethod
    async def update(cls, session: AsyncSession, data: SellerUpdate, seller_id: UUID) -> SellerModel:
        seller = await cls.get_by_id(session, seller_id)
        if seller is None:
            raise SELLER_NOT_FOUND

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(seller, key, value)

        session.add(seller)
        await session.commit()
        await session.refresh(seller)
        return seller

    @classmethod
    async def delete(cls, session: AsyncSession, seller_id: UUID) -> None:
        seller = await cls.get_by_id(session, seller_id)
        if seller is None:
            raise SELLER_NOT_FOUND

        seller.is_active = False
        session.add(seller)
        await session.commit()

    @staticmethod
    def _resolve_image_extension(filename: str, content_type: str) -> str:
        if "." in filename:
            extension = filename.rsplit(".", 1)[-1].lower().strip()
            if extension:
                return extension
        content_type_to_extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
            "image/bmp": "bmp",
        }
        return content_type_to_extension.get(content_type, "bin")

    @staticmethod
    def _extract_object_key_from_public_url(photo_url: str, *, bucket_name: str) -> str | None:
        parsed = urlparse(photo_url)
        path = parsed.path.lstrip("/")
        bucket_prefix = f"{bucket_name}/"
        if not path.startswith(bucket_prefix):
            return None
        object_key = path[len(bucket_prefix):]
        return object_key or None

    @classmethod
    async def upload_seller_photo(
        cls,
        session: AsyncSession,
        seller_id: UUID,
        file: UploadFile,
    ) -> SellerModel:
        from app.services.minio_service import MinioService

        seller = await cls.get_seller_by_id(session, seller_id)
        if seller is None:
            raise SELLER_NOT_FOUND

        content_type = file.content_type or "application/octet-stream"
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image files are allowed",
            )

        file_data = await file.read()
        if not file_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image is empty",
            )

        minio_service = MinioService()
        file_extension = cls._resolve_image_extension(file.filename or "", content_type)
        object_key = f"sellers/{seller_id}/avatar_{uuid4()}.{file_extension}"
        photo_url = minio_service.upload_file(
            file_data=file_data,
            filename=object_key,
            content_type=content_type,
        )

        previous_photo_url = seller.photo_url.strip() if isinstance(seller.photo_url, str) else None
        seller.photo_url = photo_url
        session.add(seller)
        await session.commit()
        await session.refresh(seller)

        if previous_photo_url:
            previous_object_key = cls._extract_object_key_from_public_url(
                previous_photo_url,
                bucket_name=minio_service.bucket_name,
            )
            if previous_object_key and previous_object_key != object_key:
                try:
                    minio_service.delete_file(previous_object_key)
                except HTTPException:
                    pass

        return seller
