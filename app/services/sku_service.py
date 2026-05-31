import logging
from uuid import uuid4, UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.images import SKUImageModel
from app.models.products import ProductModel, ProductStatus
from app.models.skus import SKUModel
from app.schemas import SKUCreate, SKUUpdate

logger = logging.getLogger(__name__)


class SKUService:
    @classmethod
    async def get_by_product(cls, session: AsyncSession, product_id: UUID) -> list[SKUModel]:
        stmt = (
            select(SKUModel)
            .where(SKUModel.product_id == product_id)
            .options(selectinload(SKUModel.images))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_by_id(cls, session: AsyncSession, sku_id: UUID) -> SKUModel:
        stmt = (
            select(SKUModel)
            .where(SKUModel.id == sku_id)
            .options(selectinload(SKUModel.images))
        )
        sku = await session.scalar(stmt)
        if sku is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "SKU not found"},
            )
        return sku

    @classmethod
    async def _verify_product_ownership(
        cls,
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID,
    ) -> ProductModel:
        product = await session.get(ProductModel, product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Product not found"},
            )
        if product.seller_id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "NOT_OWNER", "message": "Product does not belong to the authenticated seller"},
            )
        return product

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        data: SKUCreate,
        seller_id: UUID,
    ) -> SKUModel:
        product = await cls._verify_product_ownership(session, data.product_id, seller_id)

        if product.status == ProductStatus.HARD_BLOCKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Cannot add SKU to hard-blocked product"},
            )

        if not data.images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REQUEST", "message": "image is required"},
            )

        is_first_sku = product.status == ProductStatus.CREATED
        # Canon B2B-2 (rule from 2026-05-27): adding SKU to MODERATED/BLOCKED also triggers re-moderation
        triggers_edit = product.status in (ProductStatus.MODERATED, ProductStatus.BLOCKED)

        # Capture json_before snapshot BEFORE adding the new SKU (needed for EDITED event payload)
        json_before = None
        if triggers_edit:
            from app.schemas import ProductResponse as _PR
            from app.services.product_service import ProductService
            full_before = await ProductService._load_full(session, product.id)
            raw = _PR.model_validate(full_before).model_dump(mode="json")
            for s in raw.get("skus", []):
                s.pop("cost_price", None)
                s.pop("reserved_quantity", None)
            json_before = raw

        characteristics = [
            {"id": str(uuid4()), "name": c.name, "value": c.value}
            for c in (data.characteristics or [])
        ]

        sku = SKUModel(
            product_id=data.product_id,
            name=data.name,
            price=data.price,
            discount=data.discount,
            cost_price=data.cost_price,
            article=data.article,
            characteristics=characteristics,
        )
        session.add(sku)
        await session.flush()

        for img in data.images:
            session.add(SKUImageModel(sku_id=sku.id, url=img.url, ordering=img.ordering))

        if is_first_sku or triggers_edit:
            product.status = ProductStatus.ON_MODERATION

        await session.commit()

        # Fire after commit so the transaction is safe regardless of Moderation availability
        from app.services.event_service import send_product_event_to_moderation
        if is_first_sku:
            await send_product_event_to_moderation(session, data.product_id, product.seller_id, "CREATED")
        elif triggers_edit:
            await send_product_event_to_moderation(session, data.product_id, product.seller_id, "EDITED", json_before=json_before)

        stmt = select(SKUModel).where(SKUModel.id == sku.id).options(selectinload(SKUModel.images))
        return await session.scalar(stmt)

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        sku_id: UUID,
        data: SKUUpdate,
        seller_id: UUID,
    ) -> SKUModel:
        sku = await cls.get_by_id(session, sku_id)

        product = await cls._verify_product_ownership(session, sku.product_id, seller_id)

        if product.status == ProductStatus.HARD_BLOCKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Cannot edit SKU of a hard-blocked product"},
            )

        needs_moderation = product.status in (ProductStatus.MODERATED, ProductStatus.BLOCKED)

        # Capture json_before snapshot BEFORE applying changes (required by moderation OpenAPI EventProductEdited)
        json_before = None
        if needs_moderation:
            from app.schemas import ProductResponse as _PR
            from app.services.product_service import ProductService
            full_before = await ProductService._load_full(session, product.id)
            raw = _PR.model_validate(full_before).model_dump(mode="json")
            for s in raw.get("skus", []):
                s.pop("cost_price", None)
                s.pop("reserved_quantity", None)
            json_before = raw

        update_data = data.model_dump(exclude_unset=True)

        if "characteristics" in update_data and update_data["characteristics"] is not None:
            update_data["characteristics"] = [
                {"id": str(uuid4()), "name": c["name"], "value": c["value"]}
                for c in update_data["characteristics"]
            ]

        for field, value in update_data.items():
            setattr(sku, field, value)

        session.add(sku)
        await session.flush()

        if needs_moderation:
            product.status = ProductStatus.ON_MODERATION
            session.add(product)
            await session.flush()
            from app.services.event_service import send_product_event_to_moderation
            await send_product_event_to_moderation(session, product.id, product.seller_id, "EDITED", json_before=json_before)

        await session.commit()

        stmt = select(SKUModel).where(SKUModel.id == sku.id).options(selectinload(SKUModel.images))
        return await session.scalar(stmt)

    @classmethod
    async def delete(
        cls,
        session: AsyncSession,
        sku_id: UUID,
        seller_id: UUID,
    ) -> None:
        sku = await cls.get_by_id(session, sku_id)

        # Ownership must be checked before any state-leaking check (IDOR prevention)
        product = await cls._verify_product_ownership(session, sku.product_id, seller_id)

        if product.status == ProductStatus.HARD_BLOCKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Cannot delete SKU of hard-blocked product"},
            )

        if sku.reserved_quantity > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CONFLICT", "message": "Cannot delete SKU with active reserves"},
            )

        product_id = sku.product_id
        product_seller_id = product.seller_id
        was_on_moderation = product.status == ProductStatus.ON_MODERATION
        was_moderated = product.status == ProductStatus.MODERATED
        sku_had_stock = sku.stock_quantity - sku.reserved_quantity > 0
        sku_id_copy = sku.id

        await session.delete(sku)
        await session.flush()

        remaining = await session.scalar(
            select(func.count()).select_from(SKUModel).where(SKUModel.product_id == product_id)
        )
        if remaining == 0 and was_on_moderation:
            product.status = ProductStatus.CREATED
            session.add(product)

        await session.commit()

        from app.services.event_service import send_product_event_to_moderation, send_sku_out_of_stock
        if remaining == 0 and was_on_moderation:
            await send_product_event_to_moderation(session, product_id, product_seller_id, "DELETED")
        if was_moderated and sku_had_stock:
            await send_sku_out_of_stock([sku_id_copy])
