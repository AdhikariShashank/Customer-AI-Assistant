
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    __table_args__ = (
        CheckConstraint(
            "requested_amount >= 0",
            name="ck_approval_requests_amount_non_negative",
        ),
        Index(
            "uq_approval_requests_pending_cart",
            "cart_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_approval_requests_requested_at",
            "requested_at",
        ),
        UniqueConstraint(
            "execution_id",
            "waiting_task_id",
            name="uq_approval_execution_task",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Customer who requested approval.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    # Cart associated with the approval request.
    cart_id: Mapped[int] = mapped_column(
        ForeignKey("carts.id"),
        index=True,
        nullable=False,
    )

    # Operation requiring approval, e.g. place_order.
    operation: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=ApprovalStatus.PENDING.value,
        server_default=ApprovalStatus.PENDING.value,
        index=True,
        nullable=False,
    )

    # Governance policy that triggered approval.
    policy_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    reason_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Amount presented for administrator review.
    requested_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    # Immutable snapshot of the cart when approval was requested.
    cart_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Administrator who reviewed the request.
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Set when the approval is successfully used for checkout.
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Order created using this approval.
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"),
        unique=True,
        nullable=True,
    )

    # Relationships.
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="requested_approvals",
    )

    reviewer = relationship(
        "User",
        foreign_keys=[reviewed_by],
        back_populates="reviewed_approvals",
    )

    cart = relationship(
        "Cart",
        back_populates="approval_requests",
    )

    order = relationship("Order")

    execution_id: Mapped[int] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    waiting_task_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    execution = relationship("AgentExecution")
