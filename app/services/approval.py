
import logging
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.models.approval_request import ApprovalRequest, ApprovalStatus
from app.planner.operations import OperationSpec
from app.repositories.agent_execution import AgentExecutionRepository
from app.repositories.approval import ApprovalRepository
from app.services.execution_resolution import ExecutionResolutionService
from app.core.config import get_settings


logger = logging.getLogger(__name__)


# Must match the actual PostgreSQL partial unique index name.
PENDING_APPROVAL_UNIQUE_INDEX = "uq_approval_requests_pending_cart"




class ApprovalService:
    def __init__(
        self,
        repository: ApprovalRepository,
        execution_repository: AgentExecutionRepository,
        operation_registry: dict[str, OperationSpec],
        approval_ttl: timedelta | None = None,
    ) -> None:
        self.repository = repository
        self.execution_repository = execution_repository

        self.execution_resolution_service = ExecutionResolutionService(
            execution_repository=execution_repository,
            operation_registry=operation_registry,
        )

        settings = get_settings()

        self.approval_ttl = (
            approval_ttl
            if approval_ttl is not None
            else timedelta(
                minutes=settings.approval_expiration_duration_minutes
            )
        )

    async def expire_pending_approvals(
        self,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Expire pending approval requests whose expiry time has passed.

        Each expired approval is also used to resolve its associated
        waiting execution with an APPROVAL_EXPIRED outcome.
        """

        if limit < 1:
            raise AppException(
                code="INVALID_BATCH_LIMIT",
                message="Expiry batch limit must be greater than zero.",
            )

        now = datetime.now(timezone.utc)

        expired_approvals = (
            await self.repository.get_expired_pending_for_update(
                now=now,
                limit=limit,
            )
        )

        expired_approval_ids: list[int] = []

        for approval in expired_approvals:
            # Mark the approval as expired.
            await self.repository.mark_expired(approval)

            # Resolve the associated execution, if one exists.
            await self._resolve_execution(
                approval=approval,
                outcome="expired",
            )

            expired_approval_ids.append(approval.id)

        logger.info(
            "Approval expiry batch completed. processed_count=%s",
            len(expired_approval_ids),
        )

        return {
            "processed_count": len(expired_approval_ids),
            "expired_approval_ids": expired_approval_ids,
        }

    async def _resolve_execution(
        self,
        approval: ApprovalRequest,
        outcome: Literal["rejected", "expired"],
    ) -> None:
        """Resolve the execution associated with a rejected/expired approval."""

        if not approval.execution_id or not approval.waiting_task_id:
            raise AppException(
                code="INVALID_APPROVAL_REFERENCE",
                message="Approval is missing its execution or waiting task reference.",
            )

        execution = await self.execution_repository.get_by_id_for_update(
            approval.execution_id
        )

        if execution is None:
            raise AppException(
                code="EXECUTION_NOT_FOUND",
                message=(
                    f"Execution {approval.execution_id} associated "
                    "with this approval was not found."
                ),
            )

        await self.execution_resolution_service.resolve_approval(
            execution=execution,
            task_id=approval.waiting_task_id,
            outcome=outcome,
            approval_id=approval.id,
        )

        logger.info(
            "approval.execution_resolved approval_id=%s "
            "execution_id=%s outcome=%s",
            approval.id,
            execution.id,
            outcome,
        )

    # --------------------------------------------------
    # COMMON VALIDATION
    # --------------------------------------------------

    @staticmethod
    def _validate_positive_id(
        value: Any,
        field_name: str,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise AppException(
                code=f"INVALID_{field_name.upper()}",
                message=f"A valid {field_name.replace('_', ' ')} is required.",
            )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        """Normalize a datetime to timezone-aware UTC."""

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    # --------------------------------------------------
    # 1. GET PENDING APPROVALS
    # --------------------------------------------------

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
    # 2. VALIDATE CHECKOUT FACTS
    # --------------------------------------------------

    def _validate_checkout_facts(
        self,
        checkout_facts: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Validate trusted checkout facts before creating an approval.

        Checkout facts must originate from the backend OrderService,
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

        self._validate_positive_id(cart_id, "cart_id")

        if not isinstance(cart_snapshot, dict):
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot is missing or invalid.",
            )

        snapshot_cart_id = cart_snapshot.get("cart_id")
        snapshot_total = cart_snapshot.get("total_amount")
        snapshot_currency = cart_snapshot.get("currency")
        items = cart_snapshot.get("items")

        if (
            isinstance(snapshot_cart_id, bool)
            or not isinstance(snapshot_cart_id, int)
            or snapshot_cart_id != cart_id
        ):
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

        if (
            not isinstance(currency, str)
            or not isinstance(snapshot_currency, str)
        ):
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
    # 3. CREATE APPROVAL REQUEST
    # --------------------------------------------------

    async def create_request(
        self,
        user_id: int,
        execution_id: int,
        waiting_task_id: str,
        checkout_facts: dict[str, Any],
        policy_id: str,
        reason_code: str,
    ) -> ApprovalRequest:
        """Create a pending approval request for checkout."""

        self._validate_positive_id(user_id, "user_id")
        self._validate_positive_id(execution_id, "execution_id")

        if (
            not isinstance(waiting_task_id, str)
            or not waiting_task_id.strip()
        ):
            raise AppException(
                code="INVALID_TASK_ID",
                message="A valid waiting task ID is required.",
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
            expires_at = self._normalize_datetime(
                existing_request.expires_at
            )

            if expires_at <= now:
                await self.repository.mark_expired(existing_request)
                await self._resolve_execution(
                    approval=existing_request,
                    outcome="expired",
                )

                logger.info(
                    "Previous approval request expired. "
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
            execution_id=execution_id,
            waiting_task_id=waiting_task_id,
            expires_at=now + self.approval_ttl,
        )

        try:
            created_request = await self.repository.create(
                approval_request
            )

        except IntegrityError as exc:
            original_error = getattr(exc, "orig", None)
            diagnostics = getattr(original_error, "diag", None)
            constraint_name = getattr(
                diagnostics,
                "constraint_name",
                None,
            )

            if constraint_name == PENDING_APPROVAL_UNIQUE_INDEX:
                logger.warning(
                    "Concurrent duplicate approval request detected. "
                    "user_id=%s cart_id=%s constraint=%s",
                    user_id,
                    cart_id,
                    constraint_name,
                )

                raise AppException(
                    code="APPROVAL_ALREADY_PENDING",
                    message="An approval request is already pending for this cart.",
                ) from exc

            logger.exception(
                "Approval request database integrity error. "
                "user_id=%s cart_id=%s constraint=%s",
                user_id,
                cart_id,
                constraint_name,
            )
            raise

        logger.info(
            "Approval request created. "
            "approval_id=%s user_id=%s cart_id=%s "
            "execution_id=%s waiting_task_id=%s amount=%s currency=%s",
            created_request.id,
            user_id,
            cart_id,
            execution_id,
            waiting_task_id,
            facts["order_total"],
            facts["currency"],
        )

        return created_request

    # --------------------------------------------------
    # 4. GET APPROVAL REQUEST
    # --------------------------------------------------

    async def get_request(
        self,
        approval_id: int,
    ) -> ApprovalRequest:
        self._validate_positive_id(approval_id, "approval_id")

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
    # 5. GET USER APPROVAL HISTORY
    # --------------------------------------------------

    async def get_user_approvals(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ApprovalRequest]:

        self._validate_positive_id(user_id, "user_id")

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
    # 6. SHARED APPROVAL REVIEW
    # --------------------------------------------------

    
    async def _review_request(
        self,
        approval_id: int,
        reviewer_id: int,
        status: ApprovalStatus,
        comment: str | None,
    ) -> ApprovalRequest:

        self._validate_positive_id(approval_id, "approval_id")
        self._validate_positive_id(reviewer_id, "reviewer_id")

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
        expires_at = self._normalize_datetime(approval.expires_at)

        # Handle expiration during admin review.
        if expires_at <= now:
            await self.repository.mark_expired(approval)

            await self._resolve_execution(
                approval=approval,
                outcome="expired",
            )

            logger.info(
                "Approval request expired during review. approval_id=%s",
                approval_id,
            )

            return approval

        # Update approval review status.
        updated_approval = await self.repository.update_review(
            approval=approval,
            status=status,
            reviewed_by=reviewer_id,
            reviewed_at=now,
            review_comment=comment,
        )

        # Rejection must also resolve the associated execution.
        if status == ApprovalStatus.REJECTED:
            await self._resolve_execution(
                approval=updated_approval,
                outcome="rejected",
            )

        logger.info(
            "Approval request reviewed. "
            "approval_id=%s reviewer_id=%s status=%s",
            approval_id,
            reviewer_id,
            status.value,
        )

        return updated_approval


    # --------------------------------------------------
    # 7. APPROVE
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
    # 8. REJECT
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
