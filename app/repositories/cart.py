import logging
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import Cart
from app.models.cart_item import CartItem

logger = logging.getLogger(__name__)


class CartRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_cart(
        self, user_id: int
    ) -> Cart | None:
        logger.debug(
            "Fetching active cart for user_id=%s",
            user_id,
        )

        try:
            stmt = (
                select(Cart)
                .where(
                    Cart.user_id == user_id,
                    Cart.status == "ACTIVE",
                )
                .options(
                    selectinload(Cart.items).selectinload(
                        CartItem.product
                    )
                )
            )
            result = await self.db.execute(stmt)
            cart = result.scalar_one_or_none()

            if cart:
                logger.debug(
                    "Active cart found: cart_id=%s, user_id=%s",
                    cart.id,
                    user_id,
                )
            else:
                logger.debug(
                    "No active cart found for user_id=%s",
                    user_id,
                )

            return cart

        except Exception:
            logger.exception(
                "Failed to fetch active cart for user_id=%s",
                user_id,
            )
            raise

    async def create_cart(self, user_id: int) -> Cart:
        logger.info(
            "Creating active cart for user_id=%s",
            user_id,
        )

        try:
            cart = Cart(user_id=user_id, status="ACTIVE")
            self.db.add(cart)
            await self.db.flush()
            await self.db.refresh(cart)

            logger.info(
                "Active cart created: cart_id=%s, user_id=%s",
                cart.id,
                user_id,
            )
            return cart

        except Exception:
            logger.exception(
                "Failed to create cart for user_id=%s",
                user_id,
            )
            raise

    async def get_item(
        self,
        cart_id: int,
        product_id: int,
    ) -> CartItem | None:
        logger.debug(
            "Fetching cart item for cart_id=%s, product_id=%s",
            cart_id,
            product_id,
        )

        try:
            stmt = select(CartItem).where(
                CartItem.cart_id == cart_id,
                CartItem.product_id == product_id,
            )
            result = await self.db.execute(stmt)
            item = result.scalar_one_or_none()

            if item:
                logger.debug(
                    "Cart item found: item_id=%s, cart_id=%s",
                    item.id,
                    cart_id,
                )
            else:
                logger.debug(
                    "Cart item not found: cart_id=%s, product_id=%s",
                    cart_id,
                    product_id,
                )

            return item

        except Exception:
            logger.exception(
                "Failed to fetch cart item for cart_id=%s, product_id=%s",
                cart_id,
                product_id,
            )
            raise

    async def get_user_cart_item(
        self,
        user_id: int,
        item_id: int,
    ) -> CartItem | None:
        logger.debug(
            "Fetching cart item for user_id=%s, item_id=%s",
            user_id,
            item_id,
        )

        try:
            stmt = (
                select(CartItem)
                .join(Cart, Cart.id == CartItem.cart_id)
                .where(
                    CartItem.id == item_id,
                    Cart.user_id == user_id,
                    Cart.status == "ACTIVE",
                )
                .options(selectinload(CartItem.product))
            )
            result = await self.db.execute(stmt)
            item = result.scalar_one_or_none()

            if item:
                logger.debug(
                    "User cart item found: item_id=%s, user_id=%s",
                    item_id,
                    user_id,
                )
            else:
                logger.debug(
                    "User cart item not found: item_id=%s, user_id=%s",
                    item_id,
                    user_id,
                )

            return item

        except Exception:
            logger.exception(
                "Failed to fetch user cart item: user_id=%s, item_id=%s",
                user_id,
                item_id,
            )
            raise

    async def add_item(
        self,
        cart_id: int,
        product_id: int,
        quantity: int,
        unit_price: Decimal,
    ) -> CartItem:
        logger.info(
            "Adding item to cart: cart_id=%s, product_id=%s, quantity=%s",
            cart_id,
            product_id,
            quantity,
        )

        try:
            item = CartItem(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
            )
            self.db.add(item)
            await self.db.flush()
            await self.db.refresh(item)

            logger.info(
                "Cart item added: item_id=%s, cart_id=%s, product_id=%s",
                item.id,
                cart_id,
                product_id,
            )
            return item

        except Exception:
            logger.exception(
                "Failed to add item to cart: cart_id=%s, product_id=%s",
                cart_id,
                product_id,
            )
            raise

    
    async def update_item(
        self,
        item_id: int,
        quantity: int,
    ) -> CartItem:
        logger.info(
            "Incrementing cart item quantity: item_id=%s, quantity_to_add=%s",
            item_id,
            quantity,
        )

        try:
            stmt = (
                update(CartItem)
                .where(CartItem.id == item_id)
                .values(
                    quantity= quantity
                )
                .returning(CartItem.id)
            )

            result = await self.db.execute(stmt)
            updated_item_id = result.scalar_one_or_none()

            if updated_item_id is None:
                logger.warning(
                    "Cart item not found for update: item_id=%s",
                    item_id,
                )
                raise ValueError(f"Cart item {item_id} not found")

            result = await self.db.execute(
                select(CartItem).where(
                    CartItem.id == updated_item_id
                )
            )
            item = result.scalar_one()

            logger.info(
                "Cart item quantity incremented: item_id=%s, new_quantity=%s",
                item.id,
                item.quantity,
            )

            return item

        except Exception:
            logger.exception(
                "Failed to increment cart item quantity: item_id=%s",
                item_id,
            )
            raise

    async def remove_item(self, item_id: int) -> None:
        logger.info(
            "Removing cart item: item_id=%s",
            item_id,
        )

        try:
            result = await self.db.execute(
                select(CartItem).where(CartItem.id == item_id)
            )
            item = result.scalar_one()
            await self.db.delete(item)
            await self.db.flush()

            logger.info(
                "Cart item removed: item_id=%s",
                item_id,
            )

        except Exception:
            logger.exception(
                "Failed to remove cart item: item_id=%s",
                item_id,
            )
            raise
