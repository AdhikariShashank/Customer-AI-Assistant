from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.approval_request import ApprovalStatus


from pydantic import field_validator


class ApprovalReviewRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    comment: str | None = Field(
        default=None,
        max_length=1000,
    )

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        return value or None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    cart_id: int
    operation: str
    status: ApprovalStatus
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