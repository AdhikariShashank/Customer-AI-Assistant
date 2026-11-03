from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base



class ExecutionStatus(str, Enum):
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plan: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    results: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    task_statuses: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
    )

    waiting_task_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ExecutionStatus.RUNNING.value,
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

    __table_args__ = (
        Index(
            "ix_agent_executions_user_status",
            "user_id",
            "status",
        ),
    )