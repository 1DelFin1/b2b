from uuid import uuid4, UUID

from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductImageModel(Base):
    __tablename__ = "product_images"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(1024))
    alt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ordering: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SKUImageModel(Base):
    __tablename__ = "sku_images"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    sku_id: Mapped[UUID] = mapped_column(
        ForeignKey("skus.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(1024))
    alt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ordering: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
