from uuid import uuid4, UUID

from sqlalchemy import String, Boolean, Float, Integer
from sqlalchemy.orm import mapped_column, Mapped

from app.core.database import Base
from app.models.mixins import TimestampMixin


class SellerModel(Base, TimestampMixin):
    __tablename__ = "sellers"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True, unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_name: Mapped[str] = mapped_column(String(255))
    inn: Mapped[str] = mapped_column(String(12))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String)
    rating: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    orders_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
