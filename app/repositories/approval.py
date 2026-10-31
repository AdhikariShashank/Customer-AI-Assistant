from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_request import ApprovalRequest, ApprovalStatus


class ApprovalRepository:
    """Handles database persistence for approval requests."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        approval_request: ApprovalRequest,
    ) -> ApprovalRequest:
        """Create a new approval request."""

        self.db.add(approval_request)

        await self.db.flush()
        await self.db.refresh(approval_request)

        return approval_request

    async def get_by_id(
        self,
        approval_id: int,
    ) -> ApprovalRequest | None:
        """Retrieve an approval request by ID."""

        stmt = select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_pending_by_cart(
        self,
        cart_id: int,
    ) -> ApprovalRequest | None:
        """Retrieve the pending approval request for a cart."""

        stmt = select(ApprovalRequest).where(
            ApprovalRequest.cart_id == cart_id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_pending_for_update(
        self,
        approval_id: int,
    ) -> ApprovalRequest | None:
        """Retrieve and lock a pending approval request."""

        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
            )
            .with_for_update()
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_user_approvals(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        """Retrieve approval history for a customer."""

        stmt = (
            select(ApprovalRequest)
            .where(ApprovalRequest.user_id == user_id)
            .order_by(ApprovalRequest.requested_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def update_review(
        self,
        approval_request: ApprovalRequest,
        *,
        status: ApprovalStatus,
        reviewed_by: int,
        reviewed_at: datetime,
        review_comment: str | None = None,
    ) -> ApprovalRequest:
        """Update the review decision and reviewer details."""

        approval_request.status = status.value
        approval_request.reviewed_by = reviewed_by
        approval_request.reviewed_at = reviewed_at
        approval_request.review_comment = review_comment

        await self.db.flush()
        await self.db.refresh(approval_request)

        return approval_request