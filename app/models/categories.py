from datetime import datetime
from uuid import uuid4, UUID

from sqlalchemy import String, Boolean, Integer, ForeignKey, func, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CategoryModel(Base):
    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    path: Mapped[str] = mapped_column(String(1000), default="", server_default="''")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
