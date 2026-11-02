from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExpirationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processed_count: int
    expired_count: int
    failed_count: int
    skipped_count: int = 0

class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    cart_id: int
    operation: str
    status: str

    policy_id: str
    reason_code: str

    requested_amount: Decimal
    currency: str
    cart_snapshot: dict[str, Any]

    requested_at: datetime
    expires_at: datetime

    reviewed_by: int | None
    reviewed_at: datetime | None
    review_comment: str | None

    consumed_at: datetime | None
    order_id: int | None


class ApprovalReviewRequest(BaseModel):
    comment: str | None = Field(
        default=None,
        max_length=1000,
    )