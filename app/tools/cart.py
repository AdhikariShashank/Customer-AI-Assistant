
import logging
from decimal import Decimal
from typing import AsyncContextManager, Callable

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from app.services.cart import CartService


logger = logging.getLogger(__name__)


CartServiceContextFactory = Callable[
    [],
    AsyncContextManager[CartService],
]


class EmptyCartInput(BaseModel):
    """No user-provided arguments are required."""

    model_config = ConfigDict(extra="forbid")


class AddCartItemInput(BaseModel):
    """Arguments required to add a product to the cart."""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(
        ge=1,
        description="ID of the product to add to the cart.",
    )
    quantity: int = Field(
        ge=1,
        description="Positive quantity of the product to add.",
    )


class RemoveCartItemInput(BaseModel):
    """Arguments required to remove a cart item."""

    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(
        ge=1,
        description="ID of the item in the user's cart to remove.",
    )


def _get_authenticated_user_id(config: RunnableConfig) -> int:
    """Read trusted identity supplied by the backend."""
    configurable = config.get("configurable") or {}
    user_id = configurable.get("user_id")

    if user_id is None:
        logger.error("Authenticated user ID missing from RunnableConfig")
        raise ValueError("Authenticated user ID is missing.")

    try:
        authenticated_user_id = int(user_id)
    except (TypeError, ValueError):
        logger.exception(
            "Invalid authenticated user ID in RunnableConfig"
        )
        raise

    logger.debug(
        "Authenticated user ID resolved: user_id=%s",
        authenticated_user_id,
    )
    return authenticated_user_id


def _serialize_cart(cart) -> dict:
    """Convert the cart ORM object into JSON-safe data."""
    logger.debug(
        "Serializing cart: cart_id=%s item_rows=%s",
        cart.id,
        len(cart.items),
    )

    items = []
    total = Decimal("0.00")

    for item in cart.items:
        unit_price = Decimal(str(item.unit_price))
        subtotal = unit_price * item.quantity
        total += subtotal

        product = getattr(item, "product", None)

        items.append({
            "item_id": item.id,
            "product_id": item.product_id,
            "name": product.name if product else None,
            "quantity": item.quantity,
            "unit_price": str(unit_price),
            "subtotal": str(subtotal),
        })

    serialized = {
        "id": cart.id,
        "status": cart.status,
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "total": str(total),
    }

    logger.info(
        "Cart serialized: cart_id=%s rows=%s item_count=%s total=%s",
        cart.id,
        len(items),
        serialized["item_count"],
        serialized["total"],
    )

    return serialized


def create_cart_tools(
    cart_service_context: CartServiceContextFactory,
):
    """Create cart tools backed by the existing CartService."""

    @tool(
        "get_active_cart",
        args_schema=EmptyCartInput,
    )
    async def get_active_cart(config: RunnableConfig) -> dict:
        """Get the authenticated customer's active shopping cart.

        Use this when the customer asks to view their cart,
        check its contents, or check the cart total.
        Do not ask the customer for a user ID.
        This tool does not modify the cart.
        """
        logger.info("Tool invoked: get_active_cart")

        try:
            user_id = _get_authenticated_user_id(config)

            logger.info(
                "get_active_cart started: user_id=%s",
                user_id,
            )

            async with cart_service_context() as service:
                logger.debug(
                    "Cart service context opened: tool=get_active_cart "
                    "user_id=%s",
                    user_id,
                )

                cart = await service.get_active_cart(user_id=user_id)

                logger.debug(
                    "Cart service call completed: tool=get_active_cart "
                    "user_id=%s cart_id=%s",
                    user_id,
                    cart.id if cart else None,
                )

            logger.debug(
                "Cart service context closed: tool=get_active_cart "
                "user_id=%s",
                user_id,
            )

            if cart is None:
                logger.info(
                    "No active cart returned: user_id=%s",
                    user_id,
                )
                return {
                    "ok": True,
                    "cart": None,
                    "message": "The customer has no active cart.",
                }

            serialized_cart = _serialize_cart(cart)

            logger.info(
                "Tool completed: get_active_cart user_id=%s cart_id=%s",
                user_id,
                cart.id,
            )

            return {
                "ok": True,
                "cart": serialized_cart,
            }

        except Exception:
            logger.exception("Tool failed: get_active_cart")
            return {
                "ok": False,
                "error": {
                    "code": "GET_CART_FAILED",
                    "message": "Unable to retrieve the cart.",
                },
            }

    @tool(
        "add_item",
        args_schema=AddCartItemInput,
    )
    async def add_item(
        product_id: int,
        quantity: int,
        config: RunnableConfig,
    ) -> dict:
        """Add a product to the authenticated customer's cart.

        Use this when the customer explicitly asks to add a product.
        Requires the product ID and a positive quantity.
        The service validates product availability and stock.
        Never accept or request a user ID from the customer.
        """
        logger.info(
            "Tool invoked: add_item product_id=%s quantity=%s",
            product_id,
            quantity,
        )

        try:
            user_id = _get_authenticated_user_id(config)

            logger.info(
                "add_item started: user_id=%s product_id=%s quantity=%s",
                user_id,
                product_id,
                quantity,
            )

            async with cart_service_context() as service:
                logger.debug(
                    "Cart service context opened: tool=add_item "
                    "user_id=%s",
                    user_id,
                )

                await service.add_item(
                    user_id=user_id,
                    product_id=product_id,
                    quantity=quantity,
                )

                logger.info(
                    "CartService.add_item returned: user_id=%s "
                    "product_id=%s quantity=%s",
                    user_id,
                    product_id,
                    quantity,
                )

                # Fetch the updated cart for the tool response.
                cart = await service.get_active_cart(user_id=user_id)

                logger.info(
                    "Updated cart fetched: user_id=%s cart_id=%s",
                    user_id,
                    cart.id if cart else None,
                )

            logger.debug(
                "Cart service context closed: tool=add_item user_id=%s",
                user_id,
            )

            serialized_cart = _serialize_cart(cart) if cart else None

            logger.info(
                "Tool completed: add_item user_id=%s product_id=%s "
                "cart_id=%s",
                user_id,
                product_id,
                cart.id if cart else None,
            )

            return {
                "ok": True,
                "message": "Product added to cart successfully.",
                "cart": serialized_cart,
            }

        except Exception:
            logger.exception(
                "Tool failed: add_item product_id=%s quantity=%s",
                product_id,
                quantity,
            )
            return {
                "ok": False,
                "error": {
                    "code": "ADD_CART_ITEM_FAILED",
                    "message": (
                        "Unable to add the product to the cart. "
                        "Check product availability and try again."
                    ),
                },
            }

    @tool(
        "remove_item",
        args_schema=RemoveCartItemInput,
    )
    async def remove_item(
        item_id: int,
        config: RunnableConfig,
    ) -> dict:
        """Remove an item from the authenticated customer's cart.

        Use this when the customer explicitly asks to remove a cart item.
        Requires the cart item's ID, not the product ID.
        The service must verify that the item belongs to this user.
        Never accept or request a user ID from the customer.
        """
        logger.info(
            "Tool invoked: remove_item item_id=%s",
            item_id,
        )

        try:
            user_id = _get_authenticated_user_id(config)

            logger.info(
                "remove_item started: user_id=%s item_id=%s",
                user_id,
                item_id,
            )

            async with cart_service_context() as service:
                logger.debug(
                    "Cart service context opened: tool=remove_item "
                    "user_id=%s",
                    user_id,
                )

                await service.remove_item(
                    user_id=user_id,
                    item_id=item_id,
                )

                logger.info(
                    "CartService.remove_item returned: user_id=%s "
                    "item_id=%s",
                    user_id,
                    item_id,
                )

                cart = await service.get_active_cart(user_id=user_id)

                logger.info(
                    "Cart fetched after removal: user_id=%s cart_id=%s",
                    user_id,
                    cart.id if cart else None,
                )

            logger.debug(
                "Cart service context closed: tool=remove_item "
                "user_id=%s",
                user_id,
            )

            serialized_cart = _serialize_cart(cart) if cart else None

            logger.info(
                "Tool completed: remove_item user_id=%s item_id=%s",
                user_id,
                item_id,
            )

            return {
                "ok": True,
                "message": "Item removed from cart successfully.",
                "cart": serialized_cart,
            }

        except Exception:
            logger.exception(
                "Tool failed: remove_item item_id=%s",
                item_id,
            )
            return {
                "ok": False,
                "error": {
                    "code": "REMOVE_CART_ITEM_FAILED",
                    "message": "Unable to remove the item from the cart.",
                },
            }

    logger.info(
        "Cart tools created: get_active_cart, add_item, remove_item"
    )

    return [get_active_cart, add_item, remove_item]
