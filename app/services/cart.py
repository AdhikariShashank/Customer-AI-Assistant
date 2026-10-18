
import logging

from app.core.exceptions import AppException
from app.repositories.cart import CartRepository
from app.repositories.product import ProductRepository

logger = logging.getLogger(__name__)


class CartService:
    def __init__(
        self,
        cart_repository: CartRepository,
        product_repository: ProductRepository,
    ):
        self.cart_repository = cart_repository
        self.product_repository = product_repository

    async def get_cart(self, user_id: int):
        logger.info("Getting cart for user_id=%s", user_id)

        cart = await self.cart_repository.get_active_cart(user_id)

        if cart is None:
            logger.info(
                "No active cart found; creating cart for user_id=%s",
                user_id,
            )
            cart = await self.cart_repository.create_cart(user_id)

        logger.info(
            "Returning cart: user_id=%s, cart_id=%s",
            user_id,
            cart.id,
        )
        return cart

    async def add_item(
        self,
        user_id: int,
        product_id: int,
        quantity: int,
    ):
        logger.info(
            "Adding item to cart: user_id=%s, product_id=%s, quantity=%s",
            user_id,
            product_id,
            quantity,
        )

        product = await self.product_repository.get_by_id(product_id)

        if product is None:
            logger.warning("Product not found: product_id=%s", product_id)
            raise AppException(
                code="PRODUCT_NOT_FOUND",
                message=f"Product with id {product_id} was not found",
            )

        logger.debug(
            "Product retrieved: product_id=%s, active=%s, stock=%s, price=%s",
            product.id,
            product.is_active,
            product.stock,
            product.price,
        )

        if not product.is_active:
            logger.warning("Inactive product requested: product_id=%s", product_id)
            raise AppException(
                code="PRODUCT_INACTIVE",
                message="This product is not available for purchase",
            )

        if quantity > product.stock:
            logger.warning(
                "Insufficient stock: product_id=%s, requested=%s, stock=%s",
                product_id,
                quantity,
                product.stock,
            )
            raise AppException(
                code="PRODUCT_OUT_OF_STOCK",
                message=f"Only {product.stock} units are available",
            )

        cart = await self.cart_repository.get_active_cart(user_id)

        if cart is None:
            logger.info("Creating cart for user_id=%s", user_id)
            cart = await self.cart_repository.create_cart(user_id)

        logger.info(
            "Using cart: user_id=%s, cart_id=%s",
            user_id,
            cart.id,
        )

        existing_item = await self.cart_repository.get_item(
            cart_id=cart.id,
            product_id=product_id,
        )

        if existing_item is not None:
            logger.info(
                "Existing cart item found: item_id=%s, current_quantity=%s",
                existing_item.id,
                existing_item.quantity,
            )
            new_quantity = existing_item.quantity + quantity
        else:
            logger.info(
                "No existing cart item found for cart_id=%s, product_id=%s",
                cart.id,
                product_id,
            )
            new_quantity = quantity

        logger.info(
            "Calculated cart item quantity: product_id=%s, new_quantity=%s",
            product_id,
            new_quantity,
        )

        if new_quantity > product.stock:
            logger.warning(
                "Requested cart quantity exceeds stock: product_id=%s, "
                "requested=%s, stock=%s",
                product_id,
                new_quantity,
                product.stock,
            )
            raise AppException(
                code="PRODUCT_OUT_OF_STOCK",
                message=f"Only {product.stock} units are available",
            )

        if existing_item is not None:
            logger.info(
                "Updating existing cart item: item_id=%s, quantity=%s",
                existing_item.id,
                new_quantity,
            )
            await self.cart_repository.update_item(
                item_id=existing_item.id,
                quantity=new_quantity,
            )
            logger.info(
                "Repository update_item completed: item_id=%s",
                existing_item.id,
            )
        else:
            logger.info(
                "Creating cart item: cart_id=%s, product_id=%s, quantity=%s",
                cart.id,
                product_id,
                quantity,
            )
            await self.cart_repository.add_item(
                cart_id=cart.id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.price,
            )
            logger.info(
                "Repository add_item completed: cart_id=%s, product_id=%s",
                cart.id,
                product_id,
            )

        updated_cart = await self.cart_repository.get_active_cart(user_id)

        logger.info(
            "Add item operation completed: user_id=%s, cart_id=%s",
            user_id,
            updated_cart.id if updated_cart else None,
        )
        return updated_cart

    async def update_item(
        self,
        user_id: int,
        item_id: int,
        quantity: int,
    ):
        logger.info(
            "Updating cart item: user_id=%s, item_id=%s, quantity=%s",
            user_id,
            item_id,
            quantity,
        )

        item = await self.cart_repository.get_user_cart_item(
            user_id=user_id,
            item_id=item_id,
        )

        if item is None:
            logger.warning(
                "Cart item not found for user: user_id=%s, item_id=%s",
                user_id,
                item_id,
            )
            raise AppException(
                code="CART_ITEM_NOT_FOUND",
                message="Cart item was not found",
            )

        logger.debug(
            "Cart item found: item_id=%s, product_id=%s, current_quantity=%s",
            item.id,
            item.product_id,
            item.quantity,
        )

        product = await self.product_repository.get_by_id(item.product_id)

        if product is None or not product.is_active:
            logger.warning(
                "Product unavailable for cart item: item_id=%s, product_id=%s",
                item_id,
                item.product_id,
            )
            raise AppException(
                code="PRODUCT_NOT_FOUND",
                message="Product is no longer available",
            )

        logger.debug(
            "Checking stock: item_id=%s, requested_quantity=%s, stock=%s",
            item_id,
            quantity,
            product.stock,
        )

        if quantity > product.stock:
            logger.warning(
                "Requested quantity exceeds stock: item_id=%s, "
                "requested=%s, stock=%s",
                item_id,
                quantity,
                product.stock,
            )
            raise AppException(
                code="PRODUCT_OUT_OF_STOCK",
                message=f"Only {product.stock} units are available",
            )

        logger.info(
            "Calling repository.update_item: item_id=%s, quantity=%s",
            item_id,
            quantity,
        )

        await self.cart_repository.update_item(
            item_id=item_id,
            quantity=quantity,
        )

        logger.info(
            "Repository update_item completed: item_id=%s",
            item_id,
        )

        updated_cart = await self.cart_repository.get_active_cart(user_id)

        logger.info(
            "Update item operation completed: user_id=%s, item_id=%s, "
            "cart_id=%s",
            user_id,
            item_id,
            updated_cart.id if updated_cart else None,
        )
        return updated_cart

    async def remove_item(self, user_id: int, item_id: int):
        logger.info(
            "Removing cart item: user_id=%s, item_id=%s",
            user_id,
            item_id,
        )

        item = await self.cart_repository.get_user_cart_item(
            user_id=user_id,
            item_id=item_id,
        )

        if item is None:
            logger.warning(
                "Cart item not found for removal: user_id=%s, item_id=%s",
                user_id,
                item_id,
            )
            raise AppException(
                code="CART_ITEM_NOT_FOUND",
                message="Cart item was not found",
            )

        logger.info(
            "Calling repository.remove_item: item_id=%s",
            item_id,
        )
        await self.cart_repository.remove_item(item_id)

        logger.info(
            "Repository remove_item completed: item_id=%s",
            item_id,
        )

        updated_cart = await self.cart_repository.get_active_cart(user_id)

        logger.info(
            "Remove item operation completed: user_id=%s, cart_id=%s",
            user_id,
            updated_cart.id if updated_cart else None,
        )
        return updated_cart

    async def get_active_cart(self, user_id: int):
        logger.info("Getting active cart: user_id=%s", user_id)

        cart = await self.cart_repository.get_active_cart(user_id)

        logger.info(
            "Active cart lookup completed: user_id=%s, cart_id=%s",
            user_id,
            cart.id if cart else None,
        )
        return cart
