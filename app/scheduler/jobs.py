import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update

from app.core.database import async_session_factory
from app.models.reserved_products import ReservedProductModel
from app.models.skus import SKUModel


logger = logging.getLogger(__name__)

RESERVATION_TTL_MINUTES = 10


async def release_expired_reservations() -> None:
    expired_before = datetime.now(timezone.utc) - timedelta(
        minutes=RESERVATION_TTL_MINUTES
    )

    async with async_session_factory() as session:
        expired_stmt = (
            select(ReservedProductModel)
            .where(ReservedProductModel.created_at <= expired_before)
            .with_for_update(skip_locked=True)
        )
        expired_rows = list((await session.scalars(expired_stmt)).all())

        if not expired_rows:
            return

        quantity_by_sku_id: dict = defaultdict(int)
        reserved_ids: list = []

        for row in expired_rows:
            quantity_by_sku_id[row.sku_id] += row.quantity
            reserved_ids.append(row.id)

        # Release reserved_quantity per SKU, flooring at 0 with GREATEST
        for sku_id, release_qty in quantity_by_sku_id.items():
            restore_stmt = (
                update(SKUModel)
                .where(SKUModel.id == sku_id)
                .values(
                    reserved_quantity=func.greatest(
                        0, SKUModel.reserved_quantity - release_qty
                    )
                )
            )
            await session.execute(restore_stmt)

        delete_stmt = delete(ReservedProductModel).where(
            ReservedProductModel.id.in_(tuple(reserved_ids))
        )
        await session.execute(delete_stmt)

        await session.commit()

    logger.info(
        "Released expired reservations: rows=%s, skus=%s",
        len(expired_rows),
        len(quantity_by_sku_id),
    )
