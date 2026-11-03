
import logging

from app.core.exceptions import AppException
from app.models.order import Order
from app.repositories.approval import ApprovalRepository
from app.repositories.order import OrderRepository
from datetime import datetime, timezone

from app.models.approval_request import ApprovalStatus


logger = logging.getLogger(__name__)


class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
        approval_repository: ApprovalRepository | None = None,
    ):
        self.repository = repository
        self.approval_repository = approval_repository


    
    async def get_checkout_facts(
        self,
        user_id: int,
    ) -> dict | None:
        """Return trusted facts used by pre-checkout governance."""

        logger.info(
            "Building checkout facts: user_id=%s",
            user_id,
        )

        return await self.repository.get_checkout_facts(
            user_id=user_id,
        )


    async def list_orders(
    self,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    ) -> tuple[list[Order], int]:
        logger.info(
            "Listing orders: user_id=%s limit=%s offset=%s",
            user_id,
            limit,
            offset,
        )

        try:
            orders, total_count = await self.repository.list_by_user(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )

            logger.info(
                "Orders retrieved successfully: "
                "user_id=%s returned_count=%s total_count=%s",
                user_id,
                len(orders),
                total_count,
            )

            return orders, total_count

        except Exception:
            logger.exception(
                "Failed to list orders: user_id=%s",
                user_id,
            )
            raise

    async def get_order(self, user_id: int, order_id: int):
        logger.info(
            "Retrieving order: user_id=%s order_id=%s",
            user_id,
            order_id,
        )

        try:
            order = await self.repository.get_by_user_and_id(
                user_id=user_id,
                order_id=order_id,
            )

            if order is None:
                logger.warning(
                    "Order not found: user_id=%s order_id=%s",
                    user_id,
                    order_id,
                )

                raise AppException(
                    code="ORDER_NOT_FOUND",
                    message=f"Order with id {order_id} was not found",
                )

            logger.info(
                "Order retrieved successfully: user_id=%s order_id=%s",
                user_id,
                order_id,
            )

            return order

        except AppException:
            raise

        except Exception:
            logger.exception(
                "Failed to retrieve order: user_id=%s order_id=%s",
                user_id,
                order_id,
            )
            raise

    async def place_order(
        self,
        user_id: int,
        approval_id: int | None = None,
        expected_snapshot: dict | None = None,
    ):
        logger.info(
            "Starting order placement: user_id=%s approval_id=%s",
            user_id,
            approval_id,
        )

        try:
            # Normal checkout: governance already allowed this operation.
            if approval_id is None:
                order = await self.repository.place_order_from_cart(
                    user_id=user_id,
                )

            else:
                if self.approval_repository is None:
                    raise AppException(
                        code="APPROVAL_SERVICE_UNAVAILABLE",
                        message="Approval verification is unavailable.",
                    )

                # Lock approval row. Concurrent retries must wait here.
                approval = (
                    await self.approval_repository.get_by_id_for_update(
                        approval_id=approval_id,
                    )
                )

                if approval is None:
                    raise AppException(
                        code="APPROVAL_NOT_FOUND",
                        message="Approval request was not found.",
                    )

                if approval.user_id != user_id:
                    raise AppException(
                        code="APPROVAL_OWNERSHIP_MISMATCH",
                        message="Approval does not belong to this user.",
                    )

                if approval.operation != "place_order":
                    raise AppException(
                        code="APPROVAL_OPERATION_MISMATCH",
                        message="Approval is not valid for checkout.",
                    )

                if approval.status != ApprovalStatus.APPROVED.value:
                    raise AppException(
                        code="APPROVAL_NOT_APPROVED",
                        message="Approval has not been approved.",
                    )

                # Idempotency: return the order if this approval
                # has already completed checkout.
                if approval.consumed_at is not None:
                    if approval.order_id is None:
                        logger.error(
                            "Consumed approval has no linked order: "
                            "approval_id=%s",
                            approval_id,
                        )
                        raise AppException(
                            code="APPROVAL_CONSUMPTION_INCONSISTENT",
                            message="Approval consumption state is inconsistent.",
                        )

                    existing_order = await self.repository.get_by_user_and_id(
                        user_id=user_id,
                        order_id=approval.order_id,
                    )

                    if existing_order is None:
                        logger.error(
                            "Consumed approval references missing order: "
                            "approval_id=%s order_id=%s",
                            approval_id,
                            approval.order_id,
                        )
                        raise AppException(
                            code="APPROVED_ORDER_NOT_FOUND",
                            message="The order associated with this approval was not found.",
                        )

                    logger.info(
                        "Returning existing order for consumed approval: "
                        "approval_id=%s order_id=%s",
                        approval_id,
                        existing_order.id,
                    )

                    return existing_order

                # A linked order without consumed_at is an inconsistent state.
                if approval.order_id is not None:
                    logger.error(
                        "Unconsumed approval already references an order: "
                        "approval_id=%s order_id=%s",
                        approval_id,
                        approval.order_id,
                    )
                    raise AppException(
                        code="APPROVAL_CONSUMPTION_INCONSISTENT",
                        message="Approval consumption state is inconsistent.",
                    )

                # Verify the executor passed the original approved snapshot.
                if (
                    not isinstance(expected_snapshot, dict)
                    or expected_snapshot != approval.cart_snapshot
                ):
                    raise AppException(
                        code="APPROVED_SNAPSHOT_MISMATCH",
                        message="Checkout snapshot does not match the approved snapshot.",
                    )

                # Repository locks the cart, items and products, then
                # validates the actual cart against the stored snapshot.
                order = await self.repository.place_order_from_cart(
                    user_id=user_id,
                    expected_snapshot=approval.cart_snapshot,
                )

                if order is None:
                    raise AppException(
                        code="ORDER_CREATION_FAILED",
                        message="Unable to create the approved order.",
                    )

                # Link order and consume approval in the SAME transaction.
                await self.approval_repository.mark_consumed(
                    approval,
                    order_id=order.id,
                    consumed_at=datetime.now(timezone.utc),
                )

            if order is None:
                logger.warning(
                    "Order repository returned no order: user_id=%s",
                    user_id,
                )
                return None

            logger.info(
                "Order placed successfully: user_id=%s order_id=%s "
                "approval_id=%s",
                user_id,
                order.id,
                approval_id,
            )

            return order

        except Exception:
            logger.exception(
                "Order placement failed: user_id=%s approval_id=%s",
                user_id,
                approval_id,
            )
            raise


    async def cancel_order(self, user_id: int, order_id: int):
        logger.info(
            "Starting order cancellation: user_id=%s order_id=%s",
            user_id,
            order_id,
        )

        try:
            order = await self.repository.get_by_user_and_id(
                user_id=user_id,
                order_id=order_id,
            )

            if order is None:
                logger.warning(
                    "Cannot cancel nonexistent order: user_id=%s order_id=%s",
                    user_id,
                    order_id,
                )

                raise AppException(
                    code="ORDER_NOT_FOUND",
                    message=f"Order with id {order_id} was not found",
                )

            status = getattr(order.status, "value", order.status)

            if status != "PLACED":
                logger.warning(
                    "Order cannot be cancelled: user_id=%s "
                    "order_id=%s status=%s",
                    user_id,
                    order_id,
                    status,
                )

                raise AppException(
                    code="ORDER_CANNOT_BE_CANCELLED",
                    message="Only placed orders can be cancelled",
                )

            cancelled_order = await self.repository.cancel_order(
                user_id=user_id,
                order_id=order_id,
            )

            logger.info(
                "Order cancelled successfully: user_id=%s order_id=%s",
                user_id,
                order_id,
            )

            return cancelled_order

        except AppException:
            raise

        except Exception:
            logger.exception(
                "Order cancellation failed: user_id=%s order_id=%s",
                user_id,
                order_id,
            )
            raise
