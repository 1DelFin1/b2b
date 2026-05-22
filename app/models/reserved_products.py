from uuid import uuid4, UUID

from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ReservedProductModel(Base, TimestampMixin):
    __tablename__ = "reserved_products"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
