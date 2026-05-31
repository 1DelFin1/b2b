from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4, UUID

from sqlalchemy import String, ForeignKey, JSON, Boolean, Text, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.images import ProductImageModel
    from app.models.skus import SKUModel
    from app.models.categories import CategoryModel


class ProductStatus(str, Enum):
    CREATED = "CREATED"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class ProductModel(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("categories.id"))
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ProductStatus.CREATED)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    blocking_reason_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    blocking_reason_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    moderator_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_reports: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="'[]'::json")
    last_moderation_idempotency_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    characteristics: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="'[]'::json"
    )
    rating: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    images: Mapped[list[ProductImageModel]] = relationship(
        "ProductImageModel", lazy="noload", cascade="all, delete-orphan",
        order_by="ProductImageModel.ordering",
    )
    skus: Mapped[list[SKUModel]] = relationship(
        "SKUModel", lazy="noload", cascade="all, delete-orphan",
    )
    category: Mapped["CategoryModel"] = relationship(
        "CategoryModel", lazy="noload", foreign_keys=[category_id],
    )

    @property
    def blocked(self) -> bool:
        return self.status in (ProductStatus.BLOCKED, ProductStatus.HARD_BLOCKED)
