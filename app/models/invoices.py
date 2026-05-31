from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4, UUID

from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    pass


class InvoiceStatus(str, Enum):
    PENDING = "PENDING"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    ACCEPTED = "ACCEPTED"
    CANCELLED = "CANCELLED"


class InvoiceModel(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(25), default=InvoiceStatus.PENDING)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    items: Mapped[list["InvoiceItemModel"]] = relationship(
        "InvoiceItemModel",
        back_populates="invoice",
        lazy="noload",
        cascade="all, delete-orphan",
    )


class InvoiceItemModel(Base):
    __tablename__ = "invoice_items"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    sku_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)
    accepted_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    invoice: Mapped["InvoiceModel"] = relationship(
        "InvoiceModel",
        back_populates="items",
        lazy="noload",
    )
