import logging

from datetime import datetime, timedelta, timezone

from psycopg import IntegrityError

from app.core.exceptions import AppException
from app.models.approval_request import ApprovalRequest, ApprovalStatus
from app.repositories.approval import ApprovalRepository

from decimal import Decimal, InvalidOperation
from typing import Any


logger = logging.getLogger(__name__)


class ApprovalService:

    def __init__(
        self,
        repository: ApprovalRepository,
        approval_ttl: timedelta = timedelta(hours=24),
    ):
        self.repository = repository
        self.approval_ttl = approval_ttl


    def _validate_checkout_facts(
        self,
        checkout_facts: dict[str, Any],
    ) -> tuple[int, Decimal, str, dict[str, Any]]:
        logger.debug("Validating checkout facts.")

        cart_id = checkout_facts.get("cart_id")
        order_total = checkout_facts.get("order_total")
        currency = checkout_facts.get("currency")
        cart_snapshot = checkout_facts.get("cart_snapshot")

        if not isinstance(cart_id, int) or cart_id <= 0:
            logger.warning(
                "Checkout facts validation failed: invalid cart_id=%s",
                cart_id,
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="A valid cart ID is required.",
            )

        if not isinstance(cart_snapshot, dict):
            logger.warning(
                "Checkout facts validation failed: invalid cart snapshot. cart_id=%s",
                cart_id,
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="A valid cart snapshot is required.",
            )

        try:
            order_total = Decimal(str(order_total))
            snapshot_total = Decimal(str(cart_snapshot.get("total_amount")))
        except (InvalidOperation, TypeError, ValueError):
            logger.warning(
                "Checkout facts validation failed: invalid amount. cart_id=%s",
                cart_id,
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Checkout amount is invalid.",
            )

        currency = str(currency).upper()

        if order_total < 0:
            logger.warning(
                "Checkout facts validation failed: negative order total. "
                "cart_id=%s order_total=%s",
                cart_id,
                order_total,
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Checkout amount cannot be negative.",
            )

        if cart_snapshot.get("cart_id") != cart_id:
            logger.warning(
                "Checkout facts validation failed: cart ID mismatch. "
                "expected_cart_id=%s snapshot_cart_id=%s",
                cart_id,
                cart_snapshot.get("cart_id"),
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot does not match the requested cart.",
            )

        if snapshot_total != order_total:
            logger.warning(
                "Checkout facts validation failed: amount mismatch. "
                "cart_id=%s order_total=%s snapshot_total=%s",
                cart_id,
                order_total,
                snapshot_total,
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot amount does not match checkout amount.",
            )

        if cart_snapshot.get("currency") != currency:
            logger.warning(
                "Checkout facts validation failed: currency mismatch. "
                "cart_id=%s expected_currency=%s snapshot_currency=%s",
                cart_id,
                currency,
                cart_snapshot.get("currency"),
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot currency does not match checkout currency.",
            )

        if not isinstance(cart_snapshot.get("items"), list):
            logger.warning(
                "Checkout facts validation failed: invalid items collection. "
                "cart_id=%s",
                cart_id,
            )
            raise AppException(
                code="INVALID_CHECKOUT_FACTS",
                message="Cart snapshot items must be a list.",
            )

        logger.debug(
            "Checkout facts validated successfully: cart_id=%s "
            "order_total=%s currency=%s item_count=%s",
            cart_id,
            order_total,
            currency,
            len(cart_snapshot["items"]),
        )

        return cart_id, order_total, currency, cart_snapshot

    
    async def create_request(
        self,
        user_id: int,
        checkout_facts: dict[str, Any],
        policy_id: str,
        reason_code: str,
    ) -> ApprovalRequest:
        logger.info(
            "Creating approval request: user_id=%s policy_id=%s",
            user_id,
            policy_id,
        )

        try:
            cart_id, order_total, currency, cart_snapshot = (
                self._validate_checkout_facts(checkout_facts)
            )

            existing = await self.repository.get_pending_by_cart(cart_id)

            if existing:
                raise AppException(
                    code="APPROVAL_ALREADY_PENDING",
                    message="A pending approval already exists for this cart.",
                )

            approval_request = ApprovalRequest(
                user_id=user_id,
                cart_id=cart_id,
                operation="place_order",
                status=ApprovalStatus.PENDING.value,
                policy_id=policy_id,
                reason_code=reason_code,
                requested_amount=order_total,
                currency=currency,
                cart_snapshot=cart_snapshot,
                expires_at=datetime.now(timezone.utc) + self.approval_ttl,
            )

            approval_request = await self.repository.create(approval_request)

            logger.info(
                "Approval request created: approval_id=%s user_id=%s cart_id=%s",
                approval_request.id,
                user_id,
                cart_id,
            )

            return approval_request

        except IntegrityError as exc:
            logger.warning(
                "Approval creation integrity conflict: user_id=%s",
                user_id,
            )

            raise AppException(
                code="APPROVAL_ALREADY_PENDING",
                message="A pending approval already exists for this cart.",
            ) from exc

        except AppException:
            raise

        except Exception:
            logger.exception(
                "Failed to create approval request: user_id=%s",
                user_id,
            )
            raise


    async def get_request(
        self,
        approval_id: int,
    ) -> ApprovalRequest:
        """Retrieve an approval request."""

        approval = await self.repository.get_by_id(
            approval_id=approval_id,
        )

        if approval is None:
            raise AppException(
                code="APPROVAL_NOT_FOUND",
                message=f"Approval request {approval_id} was not found",
            )

        return approval

    async def get_user_approvals(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        """Retrieve approval history for a customer."""

        return await self.repository.get_user_approvals(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )