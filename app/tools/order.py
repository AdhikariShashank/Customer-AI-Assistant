
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import AsyncContextManager, Callable

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from app.models.order import Order
from app.services.order import OrderService


logger = logging.getLogger(__name__)


OrderServiceContextFactory = Callable[
    [],
    AsyncContextManager[OrderService],
]


class EmptyOrderInput(BaseModel):
    """No user-provided arguments are required."""

    model_config = ConfigDict(extra="forbid")


class GetOrderInput(BaseModel):
    """Arguments required to retrieve a specific order."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ge=1,
        description="ID of the order to retrieve.",
    )


def _get_authenticated_user_id(config: RunnableConfig) -> int:
    """Get the trusted user ID supplied by the backend."""

    configurable = config.get("configurable") or {}
    user_id = configurable.get("user_id")

    if user_id is None:
        logger.error(
            "Authenticated user ID is missing from tool config."
        )
        raise ValueError("Authenticated user ID is missing.")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Invalid authenticated user ID in tool config."
        )
        raise ValueError(
            "Authenticated user ID is invalid."
        ) from exc

    if user_id < 1:
        logger.warning(
            "Authenticated user ID must be positive."
        )
        raise ValueError("Authenticated user ID is invalid.")

    return user_id


def _serialize_order_item(item) -> dict:
    """Convert an order item ORM object into JSON-safe data."""

    unit_price = Decimal(str(item.unit_price))
    quantity = item.quantity
    subtotal = unit_price * quantity

    return {
        "order_item_id": item.id,
        "product_id": item.product_id,
        "product_name": item.product_name,
        "quantity": quantity,
        "unit_price": str(unit_price),
        "subtotal": str(subtotal),
    }


def _serialize_order(order: Order) -> dict:
    """Convert a single Order ORM object into JSON-safe data."""

    if isinstance(order, (list, tuple)):
        raise TypeError(
            "Expected a single Order object, "
            f"but received {type(order).__name__} "
            f"containing {len(order)} elements."
        )

    if not isinstance(order, Order):
        raise TypeError(
            "Expected an Order ORM instance, "
            f"received {type(order).__name__}."
        )

    order_items = getattr(order, "items", None) or []

    serialized_items = [
        _serialize_order_item(item)
        for item in order_items
    ]

    # Support enum-based and string-based status values.
    status = getattr(order.status, "value", order.status)

    created_at = order.created_at

    if isinstance(created_at, (datetime, date)):
        created_at = created_at.isoformat()

    serialized = {
        "id": order.id,
        "user_id": order.user_id,
        "status": status,
        "total_amount": str(
            Decimal(str(order.total_amount))
        ),
        "created_at": created_at,
        "items": serialized_items,
    }

    logger.debug(
        "Order serialized successfully: order_id=%s item_count=%s",
        order.id,
        len(serialized_items),
    )

    return serialized


def create_order_tools(
    order_service_context: OrderServiceContextFactory,
):
    """Create LangChain tools backed by the existing OrderService."""

    @tool("list_orders", args_schema=EmptyOrderInput)
    async def list_orders(config: RunnableConfig) -> str:
        """List the authenticated customer's orders."""

        try:
            user_id = _get_authenticated_user_id(config)

            logger.info(
                "Listing orders: user_id=%s",
                user_id,
            )

            async with order_service_context() as service:
                result = await service.list_orders(
                    user_id=user_id,
                    limit=20,
                    offset=0,
                )

            logger.info(
                "Order service result: user_id=%s result_type=%s",
                user_id,
                type(result).__name__,
            )

            # Expected repository format: (orders, total_count).
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[0], (list, tuple))
                and isinstance(result[1], int)
            ):
                orders, total_count = result

            # Also support repositories returning only a list.
            elif isinstance(result, list):
                orders = result
                total_count = len(orders)

            else:
                raise TypeError(
                    "Unexpected return format from "
                    "OrderService.list_orders(): "
                    f"{type(result).__name__}."
                )

            logger.info(
                "Orders retrieved from service: user_id=%s "
                "returned_count=%s total_count=%s",
                user_id,
                len(orders),
                total_count,
            )

            # Log element types to help diagnose future mismatches.
            for index, order in enumerate(orders):
                logger.debug(
                    "Order element: index=%s type=%s",
                    index,
                    type(order).__name__,
                )

            serialized_orders = [
                _serialize_order(order)
                for order in orders
            ]

            logger.info(
                "Orders serialized successfully: "
                "user_id=%s count=%s",
                user_id,
                len(serialized_orders),
            )

            return json.dumps({
                "ok": True,
                "orders": serialized_orders,
                "count": len(serialized_orders),
                "total_count": total_count,
            })

        except Exception:
            logger.exception(
                "Failed to list orders for authenticated customer."
            )

            return json.dumps({
                "ok": False,
                "error": {
                    "code": "LIST_ORDERS_FAILED",
                    "message": "Unable to retrieve your orders.",
                },
            })

    @tool("get_order", args_schema=GetOrderInput)
    async def get_order(
        order_id: int,
        config: RunnableConfig,
    ) -> str:
        """Retrieve a specific order belonging to the authenticated customer."""

        try:
            user_id = _get_authenticated_user_id(config)

            logger.info(
                "Getting order: user_id=%s order_id=%s",
                user_id,
                order_id,
            )

            async with order_service_context() as service:
                order = await service.get_order(
                    user_id=user_id,
                    order_id=order_id,
                )

            logger.info(
                "Order service result: order_id=%s result_type=%s",
                order_id,
                type(order).__name__,
            )

            if order is None:
                logger.info(
                    "Order not found: user_id=%s order_id=%s",
                    user_id,
                    order_id,
                )

                return json.dumps({
                    "ok": True,
                    "order": None,
                    "message": "Order not found.",
                })

            serialized_order = _serialize_order(order)

            logger.info(
                "Order retrieved successfully: "
                "user_id=%s order_id=%s",
                user_id,
                order_id,
            )

            return json.dumps({
                "ok": True,
                "order": serialized_order,
            })

        except Exception:
            logger.exception(
                "Failed to retrieve order: order_id=%s",
                order_id,
            )

            return json.dumps({
                "ok": False,
                "error": {
                    "code": "GET_ORDER_FAILED",
                    "message": (
                        "Unable to retrieve the requested order."
                    ),
                },
            })

    @tool("place_order", args_schema=EmptyOrderInput)
    async def place_order(config: RunnableConfig) -> str:
        """Place an order using the authenticated customer's cart."""

        try:
            user_id = _get_authenticated_user_id(config)

            logger.info(
                "Placing order: user_id=%s",
                user_id,
            )

            async with order_service_context() as service:
                order = await service.place_order(
                    user_id=user_id,
                )

            if order is None:
                logger.warning(
                    "Order service returned no order: user_id=%s",
                    user_id,
                )

                return json.dumps({
                    "ok": False,
                    "error": {
                        "code": "ORDER_CREATION_FAILED",
                        "message": (
                            "No order was created. "
                            "Please check your cart."
                        ),
                    },
                })

            logger.info(
                "Order service result: order_id=%s result_type=%s",
                getattr(order, "id", None),
                type(order).__name__,
            )

            serialized_order = _serialize_order(order)

            logger.info(
                "Order placed successfully: "
                "user_id=%s order_id=%s",
                user_id,
                order.id,
            )

            return json.dumps({
                "ok": True,
                "message": "Order placed successfully.",
                "order": serialized_order,
            })

        except Exception:
            logger.exception(
                "Failed to place order for authenticated customer."
            )

            return json.dumps({
                "ok": False,
                "error": {
                    "code": "PLACE_ORDER_FAILED",
                    "message": (
                        "Unable to place your order. "
                        "Please check your cart and try again."
                    ),
                },
            })

    return [
        list_orders,
        get_order,
        place_order,
    ]
