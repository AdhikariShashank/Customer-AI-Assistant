
import logging

from app.core.exceptions import AppException
from app.repositories.order import OrderRepository


logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, repository: OrderRepository):
        self.repository = repository

    async def list_orders(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ):
        logger.info(
            "Listing orders: user_id=%s limit=%s offset=%s",
            user_id,
            limit,
            offset,
        )

        try:
            orders = await self.repository.list_by_user(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )

            logger.info(
                "Orders retrieved successfully: user_id=%s count=%s",
                user_id,
                len(orders),
            )

            return orders

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

    async def place_order(self, user_id: int):
        logger.info(
            "Starting order placement: user_id=%s",
            user_id,
        )

        try:
            # Repository is responsible for atomic checkout operations.
            order = await self.repository.place_order_from_cart(
                user_id=user_id,
            )

            if order is None:
                logger.warning(
                    "Order repository returned no order: user_id=%s",
                    user_id,
                )
                return None

            logger.info(
                "Order placed successfully: user_id=%s order_id=%s",
                user_id,
                order.id,
            )

            return order

        except Exception:
            logger.exception(
                "Order placement failed: user_id=%s",
                user_id,
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
