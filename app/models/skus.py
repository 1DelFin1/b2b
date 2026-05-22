from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4, UUID

from sqlalchemy import String, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.images import SKUImageModel


class SKUModel(Base, TimestampMixin):
    __tablename__ = "skus"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    article: Mapped[str | None] = mapped_column(String(100), nullable=True)
    characteristics: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="'[]'::json"
    )

    images: Mapped[list[SKUImageModel]] = relationship(
        "SKUImageModel", lazy="noload", cascade="all, delete-orphan",
        order_by="SKUImageModel.ordering",
    )

    @property
    def active_quantity(self) -> int:
        return self.stock_quantity - self.reserved_quantity
