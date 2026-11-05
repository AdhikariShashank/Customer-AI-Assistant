from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="conversation",
    )

    source_thread_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="memories",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "category",
            "key",
            name="uq_user_memory_category_key",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_user_memory_confidence",
        ),
        Index(
            "ix_user_memories_user_active",
            "user_id",
            "is_active",
        ),
    )