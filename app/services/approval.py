
import logging
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.models.approval_request import ApprovalRequest, ApprovalStatus
from app.repositories.approval import ApprovalRepository


logger = logging.getLogger(__name__)


class ApprovalService:
    """Handles the approval request lifecycle and administrator reviews."""

    def __init__(
        self,
        repository: ApprovalRepository,
        approval_ttl: timedelta = timedelta(hours=24),
    ):
        self.repository = repository
        self.approval_ttl = approval_ttl


    async def get_pending_approvals(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        """Get pending approval requests for administrators."""

        if limit < 1 or limit > 100 or offset < 0:
            raise AppException(
                code="INVALID_PAGINATION",
                message="Invalid approval pagination parameters.",
            )

        return await self.repository.get_pending_approvals(
            limit=limit,
            offset=offset,
        )

    # --------------------------------------------------
    # 1. VALIDATE CHECKOUT FACTS
    # --------------------------------------------------

    def _validate_checkout_facts(
        self,
        checkout_facts: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Validate trusted checkout facts before creating an approval.

        The checkout facts must come from the backend OrderService,
        not from planner arguments or user-provided input.
        """

        if not isinstance(checkout_facts, dict):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Valid checkout information is required.",
            )

        cart_id = checkout_facts.get("cart_id")
        order_total = checkout_facts.get("order_total")
        currency = checkout_facts.get("currency")
        cart_snapshot = checkout_facts.get("cart_snapshot")

        if not isinstance(cart_id, int) or isinstance(cart_id, bool) or cart_id <= 0:
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Invalid cart ID.",
            )

        if not isinstance(cart_snapshot, dict):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot is missing or invalid.",
            )

        snapshot_cart_id = cart_snapshot.get("cart_id")
        snapshot_total = cart_snapshot.get("total_amount")
        snapshot_currency = cart_snapshot.get("currency")
        items = cart_snapshot.get("items")

        if snapshot_cart_id != cart_id:
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart ID does not match the cart snapshot.",
            )

        if not isinstance(items, list) or not items:
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cannot request approval for an empty cart.",
            )

        if any(not isinstance(item, dict) for item in items):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot contains invalid items.",
            )

        try:
            order_total = Decimal(str(order_total))
            snapshot_total = Decimal(str(snapshot_total))
        except (InvalidOperation, TypeError, ValueError):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Invalid checkout amount.",
            )

        if (
            not order_total.is_finite()
            or not snapshot_total.is_finite()
            or order_total < 0
            or snapshot_total < 0
        ):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Checkout amount must be a valid non-negative amount.",
            )

        if order_total != snapshot_total:
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Checkout amount does not match the cart snapshot.",
            )

        if not isinstance(currency, str) or not isinstance(snapshot_currency, str):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Invalid checkout currency.",
            )

        currency = currency.upper()
        snapshot_currency = snapshot_currency.upper()

        if currency != snapshot_currency:
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Checkout currency does not match the cart snapshot.",
            )

        if currency != "INR":
            raise AppException(
                code="UNSUPPORTED_CURRENCY",
                message="Only INR checkout is currently supported.",
            )

        return {
            "cart_id": cart_id,
            "order_total": order_total,
            "currency": currency,
            "cart_snapshot": deepcopy(cart_snapshot),
        }

    # --------------------------------------------------
    # 2. CREATE APPROVAL REQUEST
    # --------------------------------------------------

    async def create_request(
        self,
        user_id: int,
        execution_id: int,
        checkout_facts: dict,
        policy_id: str,
        reason_code: str,
    ) -> ApprovalRequest:
        """Create a pending approval request for checkout."""

        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise AppException(
                code="INVALID_USER_ID",
                message="A valid authenticated user is required.",
            )

        if not isinstance(policy_id, str) or not policy_id.strip():
            raise AppException(
                code="INVALID_POLICY",
                message="A valid governance policy ID is required.",
            )

        if not isinstance(reason_code, str) or not reason_code.strip():
            raise AppException(
                code="INVALID_REASON_CODE",
                message="An approval reason code is required.",
            )

        facts = self._validate_checkout_facts(checkout_facts)

        cart_id = facts["cart_id"]

        # Prevent multiple pending approval requests for the same cart.
        existing_request = (
            await self.repository.get_pending_by_cart_for_update(cart_id)
        )

        if existing_request:
            now = datetime.now(timezone.utc)

            expires_at = existing_request.expires_at

            # Handle legacy naive datetimes safely.
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at <= now:
                await self.repository.mark_expired(existing_request)

                logger.info(
                    "Expired previous approval request: "
                    "approval_id=%s cart_id=%s",
                    existing_request.id,
                    cart_id,
                )
            else:
                raise AppException(
                    code="APPROVAL_ALREADY_PENDING",
                    message="An approval request is already pending for this cart.",
                )

        now = datetime.now(timezone.utc)

        approval_request = ApprovalRequest(
            user_id=user_id,
            cart_id=cart_id,
            operation="place_order",
            status=ApprovalStatus.PENDING.value,
            policy_id=policy_id,
            reason_code=reason_code,
            requested_amount=facts["order_total"],
            currency=facts["currency"],
            cart_snapshot=facts["cart_snapshot"],
            expires_at=now + self.approval_ttl,
        )

        try:
            created_request = await self.repository.create(
                approval_request
            )
        except IntegrityError as exc:
            # The database partial unique index protects against
            # concurrent requests for the same cart.
            logger.warning(
                "Duplicate pending approval request detected. "
                "user_id=%s cart_id=%s",
                user_id,
                cart_id,
            )

            raise AppException(
                code="APPROVAL_ALREADY_PENDING",
                message="An approval request is already pending for this cart.",
            ) from exc

        logger.info(
            "Approval request created. approval_id=%s user_id=%s "
            "cart_id=%s amount=%s currency=%s",
            created_request.id,
            user_id,
            cart_id,
            facts["order_total"],
            facts["currency"],
        )

        return created_request

    # --------------------------------------------------
    # 3. GET APPROVAL REQUEST
    # --------------------------------------------------

    async def get_request(
        self,
        approval_id: int,
    ) -> ApprovalRequest:
        approval = await self.repository.get_by_id(
            approval_id=approval_id
        )

        if approval is None:
            raise AppException(
                code="APPROVAL_NOT_FOUND",
                message="Approval request not found.",
            )

        return approval

    # --------------------------------------------------
    # 4. GET USER APPROVAL HISTORY
    # --------------------------------------------------

    async def get_user_approvals(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ApprovalRequest]:

        if limit < 1 or limit > 100 or offset < 0:
            raise AppException(
                code="INVALID_PAGINATION",
                message="Invalid approval history pagination parameters.",
            )

        return await self.repository.get_user_approvals(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    # --------------------------------------------------
    # 5. SHARED APPROVAL REVIEW
    # --------------------------------------------------

    async def _review_request(
        self,
        approval_id: int,
        reviewer_id: int,
        status: ApprovalStatus,
        comment: str | None,
    ) -> ApprovalRequest:

        approval = await self.repository.get_by_id_for_update(
            approval_id=approval_id
        )

        if approval is None:
            raise AppException(
                code="APPROVAL_NOT_FOUND",
                message="Approval request not found.",
            )

        if approval.status != ApprovalStatus.PENDING.value:
            raise AppException(
                code="APPROVAL_ALREADY_REVIEWED",
                message="This approval request is no longer pending.",
            )

        now = datetime.now(timezone.utc)

        expires_at = approval.expires_at

        # Defensive handling for a naive datetime, although the
        # database column is configured with timezone=True.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= now:
            await self.repository.mark_expired(approval)

            logger.info(
                "Approval request expired during review: approval_id=%s",
                approval_id,
            )

            raise AppException(
                code="APPROVAL_EXPIRED",
                message="This approval request has expired and cannot be reviewed.",
            )

        updated_approval = await self.repository.update_review(
            approval=approval,
            status=status,
            reviewed_by=reviewer_id,
            reviewed_at=now,
            review_comment=comment,
        )

        logger.info(
            "Approval request reviewed. approval_id=%s reviewer_id=%s status=%s",
            approval_id,
            reviewer_id,
            status.value,
        )

        return updated_approval

    # --------------------------------------------------
    # 6. APPROVE
    # --------------------------------------------------

    async def approve(
        self,
        approval_id: int,
        reviewer_id: int,
        comment: str | None = None,
    ) -> ApprovalRequest:

        return await self._review_request(
            approval_id=approval_id,
            reviewer_id=reviewer_id,
            status=ApprovalStatus.APPROVED,
            comment=comment,
        )

    # --------------------------------------------------
    # 7. REJECT
    # --------------------------------------------------

    async def reject(
        self,
        approval_id: int,
        reviewer_id: int,
        comment: str | None = None,
    ) -> ApprovalRequest:

        return await self._review_request(
            approval_id=approval_id,
            reviewer_id=reviewer_id,
            status=ApprovalStatus.REJECTED,
            comment=comment,
        )
