import logging
from uuid import uuid4, UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.categories import CategoryModel
from app.models.images import ProductImageModel
from app.models.products import ProductModel, ProductStatus
from app.models.skus import SKUModel
from app.schemas import ProductCreate, ProductUpdate, ModerationEventRequest
from app.services.event_service import send_product_event_to_moderation, send_product_event_to_b2c

logger = logging.getLogger(__name__)


class ProductService:
    @classmethod
    async def get_list(
        cls,
        session: AsyncSession,
        seller_id: UUID | None = None,
        category_id: UUID | None = None,
        status: str | None = None,
        deleted: bool = False,
        search: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        seller_id_filter: UUID | None = None,
        ids: list[UUID] | None = None,
        sort: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conditions = []

        if seller_id is not None:
            conditions.append(ProductModel.seller_id == seller_id)
            if not deleted:
                conditions.append(ProductModel.deleted == False)  # noqa: E712
        else:
            active_qty_subq = (
                select(func.coalesce(func.sum(SKUModel.stock_quantity - SKUModel.reserved_quantity), 0))
                .where(SKUModel.product_id == ProductModel.id)
                .correlate(ProductModel)
                .scalar_subquery()
            )
            conditions.append(ProductModel.status == ProductStatus.MODERATED)
            conditions.append(ProductModel.deleted == False)  # noqa: E712
            conditions.append(active_qty_subq > 0)

        if category_id is not None:
            conditions.append(ProductModel.category_id == category_id)
        if status is not None:
            conditions.append(ProductModel.status == status)
        if seller_id_filter is not None:
            conditions.append(ProductModel.seller_id == seller_id_filter)
        if ids is not None:
            conditions.append(ProductModel.id.in_(ids))
        if search is not None:
            _esc = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(
                or_(
                    ProductModel.title.ilike(f"%{_esc}%", escape="\\"),
                    ProductModel.description.ilike(f"%{_esc}%", escape="\\"),
                )
            )

        min_price_subq = (
            select(func.min(SKUModel.price))
            .where(SKUModel.product_id == ProductModel.id)
            .correlate(ProductModel)
            .scalar_subquery()
        )

        cover_image_subq = (
            select(ProductImageModel.url)
            .where(ProductImageModel.product_id == ProductModel.id)
            .order_by(ProductImageModel.ordering.asc())
            .limit(1)
            .correlate(ProductModel)
            .scalar_subquery()
        )

        skus_count_subq = (
            select(func.count(SKUModel.id))
            .where(SKUModel.product_id == ProductModel.id)
            .correlate(ProductModel)
            .scalar_subquery()
        )

        total_active_subq = (
            select(func.coalesce(func.sum(SKUModel.stock_quantity - SKUModel.reserved_quantity), 0))
            .where(SKUModel.product_id == ProductModel.id)
            .correlate(ProductModel)
            .scalar_subquery()
        )

        if min_price is not None:
            conditions.append(min_price_subq >= min_price)
        if max_price is not None:
            conditions.append(min_price_subq <= max_price)

        count_stmt = select(func.count(ProductModel.id)).where(*conditions)
        total_count = (await session.scalar(count_stmt)) or 0

        stmt = select(
            ProductModel,
            min_price_subq.label("min_price"),
            cover_image_subq.label("cover_image"),
            skus_count_subq.label("skus_count"),
            total_active_subq.label("total_active_quantity"),
        ).where(*conditions)

        if sort == "price_asc":
            stmt = stmt.order_by(min_price_subq.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(min_price_subq.desc())
        elif sort == "created_desc":
            stmt = stmt.order_by(ProductModel.created_at.desc())
        elif sort == "popular":
            stmt = stmt.order_by(ProductModel.rating.desc(), ProductModel.created_at.desc())
        else:
            stmt = stmt.order_by(ProductModel.created_at.desc())

        stmt = stmt.limit(limit).offset(offset)

        rows = (await session.execute(stmt)).all()

        results = []
        for row in rows:
            product, min_price_val, cover_image, skus_count, total_active = row
            results.append({
                "product": product,
                "min_price": min_price_val,
                "cover_image": cover_image,
                "skus_count": skus_count or 0,
                "total_active_quantity": total_active or 0,
            })

        return results, total_count

    @classmethod
    async def _load_full(cls, session: AsyncSession, product_id: UUID) -> ProductModel:
        stmt = (
            select(ProductModel)
            .where(ProductModel.id == product_id)
            .options(
                selectinload(ProductModel.category),
                selectinload(ProductModel.images),
                selectinload(ProductModel.skus).selectinload(SKUModel.images),
            )
        )
        return await session.scalar(stmt)

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID | None = None,
        public: bool = False,
    ) -> ProductModel:
        product = await cls._load_full(session, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Product not found"})
        if seller_id is not None and product.seller_id != seller_id:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Product not found"})
        if public and (product.status != ProductStatus.MODERATED or product.deleted):
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Product not found"})
        return product

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        seller_id: UUID,
        data: ProductCreate,
    ) -> ProductModel:
        if not data.images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REQUEST", "message": "At least one image is required"},
            )

        category = await session.get(CategoryModel, data.category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REQUEST", "message": "Category not found"},
            )

        slug = data.slug or data.title.lower().replace(" ", "-")
        characteristics = [
            {"id": str(uuid4()), "name": c.name, "value": c.value}
            for c in (data.characteristics or [])
        ]

        product = ProductModel(
            seller_id=seller_id,
            category_id=data.category_id,
            title=data.title,
            slug=slug,
            description=data.description,
            status=ProductStatus.CREATED,
            deleted=False,
            characteristics=characteristics,
        )
        session.add(product)
        await session.flush()

        images = [
            ProductImageModel(
                product_id=product.id,
                url=img.url,
                ordering=img.ordering,
                is_main=(img.ordering == min(i.ordering for i in data.images)),
            )
            for img in data.images
        ]
        session.add_all(images)

        await session.commit()

        loaded = await cls._load_full(session, product.id)
        return loaded

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID,
        data: ProductUpdate,
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

        if product.status == ProductStatus.HARD_BLOCKED:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "Cannot edit hard-blocked product"},
            )

        prev_status = product.status
        needs_moderation = prev_status in (ProductStatus.MODERATED, ProductStatus.BLOCKED)

        # Capture json_before snapshot BEFORE applying changes (required by moderation OpenAPI EventProductEdited)
        json_before = None
        if needs_moderation:
            from app.schemas import ProductResponse as _PR
            full_before = await cls._load_full(session, product_id)
            raw = _PR.model_validate(full_before).model_dump(mode="json")
            for sku in raw.get("skus", []):
                sku.pop("cost_price", None)
                sku.pop("reserved_quantity", None)
            json_before = raw

        update_data = data.model_dump(exclude_unset=True)

        if "characteristics" in update_data and update_data["characteristics"] is not None:
            update_data["characteristics"] = [
                {"id": str(uuid4()), "name": c["name"], "value": c["value"]}
                for c in update_data["characteristics"]
            ]

        for field, value in update_data.items():
            setattr(product, field, value)

        if needs_moderation:
            product.status = ProductStatus.ON_MODERATION
            await session.flush()
            await send_product_event_to_moderation(session, product.id, product.seller_id, "EDITED", json_before=json_before)

        session.add(product)
        await session.commit()

        loaded = await cls._load_full(session, product_id)
        return loaded

    @classmethod
    async def delete(
        cls,
        session: AsyncSession,
        product_id: UUID,
        seller_id: UUID,
    ) -> None:
        product = await session.get(ProductModel, product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        if product.deleted:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Product already deleted"},
            )
        if product.seller_id != seller_id:
            raise HTTPException(
                status_code=403,
                detail={"code": "NOT_OWNER", "message": "Product does not belong to the authenticated seller"},
            )
        if product.status == ProductStatus.HARD_BLOCKED:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "Cannot delete hard-blocked product"},
            )

        # Collect SKU IDs before deletion for cascade event
        sku_ids_stmt = select(SKUModel.id).where(SKUModel.product_id == product.id)
        sku_ids = list((await session.scalars(sku_ids_stmt)).all())

        product.deleted = True
        session.add(product)
        await session.commit()
        await send_product_event_to_moderation(session, product.id, product.seller_id, "DELETED")
        await send_product_event_to_b2c("PRODUCT_DELETED", product.id, sku_ids)

    @classmethod
    async def apply_moderation_event(
        cls,
        session: AsyncSession,
        event: ModerationEventRequest,
    ) -> None:
        product = await session.get(ProductModel, event.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Product not found"})

        # Idempotency: skip if this exact event was already applied
        if product.last_moderation_idempotency_key == str(event.idempotency_key):
            return

        incoming_event = event.event_type.upper()

        if incoming_event == "MODERATED":
            product.status = ProductStatus.MODERATED
            product.blocking_reason_id = None
            product.blocking_reason_title = None
            product.moderator_comment = None
            product.field_reports = []
        elif incoming_event == "BLOCKED":
            product.status = ProductStatus.HARD_BLOCKED if event.hard_block else ProductStatus.BLOCKED
            product.blocking_reason_id = event.blocking_reason_id
            product.moderator_comment = event.moderator_comment
            if event.field_reports is not None:
                product.field_reports = [fr.model_dump() for fr in event.field_reports]
        else:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": f"Unknown event_type: {event.event_type}"},
            )

        product.last_moderation_idempotency_key = str(event.idempotency_key)
        session.add(product)
        await session.commit()

        if incoming_event == "BLOCKED":
            sku_ids_stmt = select(SKUModel.id).where(SKUModel.product_id == product.id)
            sku_ids = list((await session.scalars(sku_ids_stmt)).all())
            await send_product_event_to_b2c("PRODUCT_BLOCKED", product.id, sku_ids)

    @classmethod
    async def get_similar(
        cls,
        session: AsyncSession,
        product_id: UUID,
        limit: int = 10,
    ) -> list[dict]:
        product = await session.get(ProductModel, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        min_price_subq = (
            select(func.min(SKUModel.price))
            .where(SKUModel.product_id == ProductModel.id)
            .correlate(ProductModel)
            .scalar_subquery()
        )
        cover_subq = (
            select(ProductImageModel.url)
            .where(ProductImageModel.product_id == ProductModel.id)
            .order_by(ProductImageModel.ordering)
            .limit(1)
            .correlate(ProductModel)
            .scalar_subquery()
        )

        def _similar_stmt(category_id: UUID) -> any:
            return (
                select(ProductModel, min_price_subq.label("min_price"), cover_subq.label("cover_image"))
                .where(
                    ProductModel.category_id == category_id,
                    ProductModel.id != product_id,
                    ProductModel.status == ProductStatus.MODERATED,
                    ProductModel.deleted == False,  # noqa: E712
                )
                .order_by(func.random())
                .limit(limit)
            )

        rows = (await session.execute(_similar_stmt(product.category_id))).all()

        # Fallback: if fewer results than requested, expand to parent category
        if len(rows) < limit:
            category = await session.get(CategoryModel, product.category_id)
            if category is not None and category.parent_id is not None:
                seen_ids = {row[0].id for row in rows}
                parent_stmt = (
                    select(ProductModel, min_price_subq.label("min_price"), cover_subq.label("cover_image"))
                    .where(
                        ProductModel.category_id == category.parent_id,
                        ProductModel.id != product_id,
                        ProductModel.id.not_in(seen_ids) if seen_ids else True,
                        ProductModel.status == ProductStatus.MODERATED,
                        ProductModel.deleted == False,  # noqa: E712
                    )
                    .order_by(func.random())
                    .limit(limit - len(rows))
                )
                parent_rows = (await session.execute(parent_stmt)).all()
                rows = rows + parent_rows

        return [{"product": row[0], "min_price": row[1], "cover_image": row[2]} for row in rows]

    @classmethod
    async def handle_review_changed(cls, event: dict) -> None:
        """Handle review event from RabbitMQ — update product rating."""
        product_id_str = event.get("product_id")
        rating = event.get("rating")
        total_reviews = event.get("total_reviews")

        if not product_id_str:
            return

        try:
            product_id = UUID(str(product_id_str))
        except (ValueError, AttributeError):
            logger.error("Invalid product_id in review event: %s", product_id_str)
            return

        from app.core.database import async_session_factory
        async with async_session_factory() as session:
            product = await session.get(ProductModel, product_id)
            if product is None:
                logger.warning("Product %s not found for review event", product_id)
                return

            if rating is not None:
                product.rating = float(rating)
            if total_reviews is not None:
                product.total_reviews = int(total_reviews)

            session.add(product)
            await session.commit()
            logger.info("Updated product %s rating=%s total_reviews=%s", product_id, rating, total_reviews)

    @classmethod
    async def reserve_product(cls, products: dict) -> None:
        """Handle reservation from RabbitMQ (orders.reserved queue)."""
        from app.core.database import async_session_factory
        from app.schemas import ReserveRequest

        try:
            data = ReserveRequest(**products)
        except Exception as exc:
            logger.error("Invalid reserve_product payload: %s — %s", products, exc)
            return

        async with async_session_factory() as session:
            from app.services.inventory_service import InventoryService
            await InventoryService.reserve(session, data)

    @classmethod
    async def handle_paid_products(cls, order: dict) -> None:
        """Fulfill (deduct stock) for paid order from RabbitMQ (products.delete queue)."""
        from app.core.database import async_session_factory
        from app.schemas import InventoryOrderRequest

        try:
            data = InventoryOrderRequest(**order)
        except Exception as exc:
            logger.error("Invalid handle_paid_products payload: %s — %s", order, exc)
            return

        async with async_session_factory() as session:
            from app.services.inventory_service import InventoryService
            await InventoryService.fulfill(session, data)
