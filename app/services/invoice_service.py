from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoices import InvoiceModel, InvoiceItemModel, InvoiceStatus
from app.models.skus import SKUModel
from app.schemas import InvoiceCreate, InvoiceAcceptRequest


class InvoiceService:

    @classmethod
    async def get_list(
        cls,
        session: AsyncSession,
        seller_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[InvoiceModel], int]:
        conditions = [InvoiceModel.seller_id == seller_id]
        if status is not None:
            conditions.append(InvoiceModel.status == status)

        count_stmt = select(func.count()).select_from(InvoiceModel).where(*conditions)
        total: int = (await session.scalar(count_stmt)) or 0

        stmt = (
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(*conditions)
            .order_by(InvoiceModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        invoices = list((await session.scalars(stmt)).all())
        return invoices, total

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        invoice_id: UUID,
        seller_id: UUID,
    ) -> InvoiceModel:
        stmt = (
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(InvoiceModel.id == invoice_id)
        )
        invoice: InvoiceModel | None = (await session.scalars(stmt)).first()

        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found",
            )
        if invoice.seller_id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found",
            )
        return invoice

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        seller_id: UUID,
        data: InvoiceCreate,
    ) -> InvoiceModel:
        if not data.items:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "At least one item is required"},
            )

        # Fetch SKU names for denormalization
        sku_ids = [item.sku_id for item in data.items]
        sku_stmt = select(SKUModel).where(SKUModel.id.in_(sku_ids))
        skus = {sku.id: sku for sku in (await session.scalars(sku_stmt)).all()}

        # Verify ownership and product status
        from app.models.products import ProductModel, ProductStatus
        for item_data in data.items:
            sku = skus.get(item_data.sku_id)
            if sku is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "NOT_FOUND", "message": "SKU not found"},
                )
            product = await session.get(ProductModel, sku.product_id)
            if product is None or product.seller_id != seller_id:
                raise HTTPException(
                    status_code=403,
                    detail={"code": "NOT_OWNER", "message": "One or more SKUs do not belong to the authenticated seller"},
                )
            if product.status != ProductStatus.MODERATED:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_REQUEST", "message": "Invoice can only be created for MODERATED products"},
                )

        invoice = InvoiceModel(
            seller_id=seller_id,
            status=InvoiceStatus.CREATED,
        )
        session.add(invoice)
        await session.flush()  # get invoice.id without committing

        items: list[InvoiceItemModel] = []
        for item_data in data.items:
            sku = skus.get(item_data.sku_id)
            item = InvoiceItemModel(
                invoice_id=invoice.id,
                sku_id=item_data.sku_id,
                sku_name=sku.name if sku else None,
                quantity=item_data.quantity,
                accepted_quantity=None,
            )
            session.add(item)
            items.append(item)

        await session.flush()
        await session.commit()

        # Re-fetch with items loaded
        stmt = (
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(InvoiceModel.id == invoice.id)
        )
        invoice = (await session.scalars(stmt)).first()
        return invoice

    @classmethod
    async def accept(
        cls,
        session: AsyncSession,
        invoice_id: UUID,
        accepted_by: UUID,
        data: InvoiceAcceptRequest,
    ) -> InvoiceModel:
        stmt = (
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(InvoiceModel.id == invoice_id)
            .with_for_update()
        )
        invoice: InvoiceModel | None = (await session.scalars(stmt)).first()

        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found",
            )
        if invoice.status not in (InvoiceStatus.CREATED, InvoiceStatus.PARTIALLY_ACCEPTED):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Invoice cannot be accepted in status '{invoice.status}'",
            )

        # When accepted_items is None or empty, perform full acceptance
        full_acceptance = data is None or not data.accepted_items

        # Build a lookup map of accepted quantities by invoice_item_id
        accepted_map: dict[str, int] = {
            str(entry.invoice_item_id): entry.accepted_quantity for entry in (data.accepted_items or [])
        }

        total_items = len(invoice.items)
        fully_accepted = 0
        any_accepted = False

        for item in invoice.items:
            accepted_qty = item.quantity if full_acceptance else accepted_map.get(str(item.id), 0)

            if accepted_qty <= 0:
                item.accepted_quantity = 0
                continue

            # Cap accepted_quantity to requested quantity
            accepted_qty = min(accepted_qty, item.quantity)
            item.accepted_quantity = accepted_qty
            any_accepted = True

            if accepted_qty == item.quantity:
                fully_accepted += 1

            # Update SKU stock
            sku_stmt = (
                select(SKUModel)
                .where(SKUModel.id == item.sku_id)
                .with_for_update()
            )
            sku: SKUModel | None = (await session.scalars(sku_stmt)).first()
            if sku is not None:
                sku.stock_quantity += accepted_qty

        # Determine new status
        if fully_accepted == total_items and total_items > 0:
            new_status = InvoiceStatus.ACCEPTED
        elif any_accepted:
            new_status = InvoiceStatus.PARTIALLY_ACCEPTED
        else:
            new_status = InvoiceStatus.CANCELLED

        invoice.status = new_status
        invoice.accepted_at = datetime.now(timezone.utc)
        invoice.accepted_by = accepted_by

        await session.commit()
        await session.refresh(invoice)

        # Re-fetch to ensure items are current
        stmt = (
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(InvoiceModel.id == invoice_id)
        )
        invoice = (await session.scalars(stmt)).first()
        return invoice

    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        invoice_id: UUID,
        seller_id: UUID,
    ) -> None:
        stmt = (
            select(InvoiceModel)
            .where(InvoiceModel.id == invoice_id)
            .with_for_update()
        )
        invoice: InvoiceModel | None = (await session.scalars(stmt)).first()

        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found",
            )
        if invoice.seller_id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        if invoice.status != InvoiceStatus.CREATED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only CREATED invoices can be cancelled, current status: '{invoice.status}'",
            )

        invoice.status = InvoiceStatus.CANCELLED
        await session.commit()
