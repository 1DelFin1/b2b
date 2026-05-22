from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reserved_products import ReservedProductModel
from app.models.skus import SKUModel
from app.schemas import ReserveRequest, ReserveResponse, ReserveResult, ReserveItemResult, ReserveFailedItem, InventoryOrderRequest, InventoryOrderResponse


class InventoryService:

    @classmethod
    async def reserve(
        cls,
        session: AsyncSession,
        data: ReserveRequest,
    ) -> ReserveResponse:
        # Idempotency check
        existing_stmt = select(ReservedProductModel).where(
            ReservedProductModel.idempotency_key == data.idempotency_key
        )
        existing = (await session.scalars(existing_stmt)).first()
        if existing is not None:
            # Already processed — return idempotent success response
            return ReserveResponse(
                order_id=data.order_id,
                status="RESERVED",
                reserved_at=datetime.now(timezone.utc),
            )

        # Lock all SKUs up front
        sku_ids = [item.sku_id for item in data.items]
        sku_stmt = (
            select(SKUModel)
            .where(SKUModel.id.in_(sku_ids))
            .with_for_update()
        )
        skus_list = list((await session.scalars(sku_stmt)).all())
        sku_map: dict[UUID, SKUModel] = {sku.id: sku for sku in skus_list}

        # Build quantity map (sum duplicates)
        qty_map: dict[UUID, int] = {}
        for item in data.items:
            qty_map[item.sku_id] = qty_map.get(item.sku_id, 0) + item.quantity

        # Check availability for all items — collect failures without raising
        failed_items: list[ReserveFailedItem] = []
        for sku_id, requested_qty in qty_map.items():
            sku = sku_map.get(sku_id)
            if sku is None:
                failed_items.append(ReserveFailedItem(
                    sku_id=sku_id,
                    requested=requested_qty,
                    available=0,
                    reason="OUT_OF_STOCK",
                ))
                continue
            available = sku.stock_quantity - sku.reserved_quantity
            if available < requested_qty:
                failed_items.append(ReserveFailedItem(
                    sku_id=sku_id,
                    requested=requested_qty,
                    available=available,
                    reason="OUT_OF_STOCK" if available == 0 else "INSUFFICIENT_STOCK",
                ))

        if failed_items:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_STOCK", "failed_items": [f.model_dump(mode="json") for f in failed_items]})

        # Apply reservations
        reserved_items: list[ReserveItemResult] = []
        out_of_stock_ids: list[UUID] = []
        for sku_id, requested_qty in qty_map.items():
            sku = sku_map[sku_id]
            sku.reserved_quantity += requested_qty
            session.add(ReservedProductModel(
                sku_id=sku_id,
                order_id=data.order_id,
                quantity=requested_qty,
                idempotency_key=data.idempotency_key,
            ))
            remaining = sku.stock_quantity - sku.reserved_quantity
            reserved_items.append(ReserveItemResult(
                sku_id=sku_id,
                reserved_quantity=requested_qty,
                remaining_stock=remaining,
            ))
            if remaining == 0:
                out_of_stock_ids.append(sku_id)

        await session.commit()

        if out_of_stock_ids:
            from app.services.event_service import send_sku_out_of_stock
            await send_sku_out_of_stock(out_of_stock_ids)

        return ReserveResponse(
            order_id=data.order_id,
            status="RESERVED",
            reserved_at=datetime.now(timezone.utc),
        )

    @classmethod
    async def unreserve(
        cls,
        session: AsyncSession,
        data: InventoryOrderRequest,
    ) -> InventoryOrderResponse:
        # Load all reservations for this order
        reservations_stmt = (
            select(ReservedProductModel)
            .where(ReservedProductModel.order_id == data.order_id)
            .with_for_update()
        )
        reservations = list((await session.scalars(reservations_stmt)).all())

        # Build quantity map from reservations (source of truth for what was reserved)
        reserved_qty_map: dict[UUID, int] = {}
        for res in reservations:
            reserved_qty_map[res.sku_id] = reserved_qty_map.get(res.sku_id, 0) + res.quantity

        if reserved_qty_map:
            sku_stmt = (
                select(SKUModel)
                .where(SKUModel.id.in_(list(reserved_qty_map.keys())))
                .with_for_update()
            )
            skus = list((await session.scalars(sku_stmt)).all())
            for sku in skus:
                release_qty = reserved_qty_map.get(sku.id, 0)
                sku.reserved_quantity = max(0, sku.reserved_quantity - release_qty)

        # Delete reservation records
        delete_stmt = delete(ReservedProductModel).where(
            ReservedProductModel.order_id == data.order_id
        )
        await session.execute(delete_stmt)
        await session.commit()

        return InventoryOrderResponse(
            order_id=data.order_id,
            status="UNRESERVED",
            processed_at=datetime.now(timezone.utc),
        )

    @classmethod
    async def fulfill(
        cls,
        session: AsyncSession,
        data: InventoryOrderRequest,
    ) -> InventoryOrderResponse:
        # Load all reservations for this order
        reservations_stmt = (
            select(ReservedProductModel)
            .where(ReservedProductModel.order_id == data.order_id)
            .with_for_update()
        )
        reservations = list((await session.scalars(reservations_stmt)).all())

        # Build quantity map from reservations
        reserved_qty_map: dict[UUID, int] = {}
        for res in reservations:
            reserved_qty_map[res.sku_id] = reserved_qty_map.get(res.sku_id, 0) + res.quantity

        if reserved_qty_map:
            sku_stmt = (
                select(SKUModel)
                .where(SKUModel.id.in_(list(reserved_qty_map.keys())))
                .with_for_update()
            )
            skus = list((await session.scalars(sku_stmt)).all())
            for sku in skus:
                deduct_qty = reserved_qty_map.get(sku.id, 0)
                sku.stock_quantity = max(0, sku.stock_quantity - deduct_qty)
                sku.reserved_quantity = max(0, sku.reserved_quantity - deduct_qty)

        # Delete reservation records
        delete_stmt = delete(ReservedProductModel).where(
            ReservedProductModel.order_id == data.order_id
        )
        await session.execute(delete_stmt)
        await session.commit()

        return InventoryOrderResponse(
            order_id=data.order_id,
            status="FULFILLED",
            processed_at=datetime.now(timezone.utc),
        )
