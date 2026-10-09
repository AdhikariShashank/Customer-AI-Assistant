
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import Cart
from app.models.cart_item import CartItem


class CartRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_cart(
        self, user_id: int
    ) -> Cart | None:
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
        return result.scalar_one_or_none()

    async def create_cart(self, user_id: int) -> Cart:
        cart = Cart(user_id=user_id, status="ACTIVE")
        self.db.add(cart)
        await self.db.flush()
        await self.db.refresh(cart)

        return cart

    async def get_item(
        self,
        cart_id: int,
        product_id: int,
    ) -> CartItem | None:
        stmt = select(CartItem).where(
            CartItem.cart_id == cart_id,
            CartItem.product_id == product_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_cart_item(
        self,
        user_id: int,
        item_id: int,
    ) -> CartItem | None:
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
        return result.scalar_one_or_none()

    async def add_item(
        self,
        cart_id: int,
        product_id: int,
        quantity: int,
        unit_price: Decimal,
    ) -> CartItem:
        item = CartItem(
            cart_id=cart_id,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)

        return item

    async def update_item(
        self,
        item_id: int,
        quantity: int,
    ) -> CartItem:
        result = await self.db.execute(
            select(CartItem).where(CartItem.id == item_id)
        )
        item = result.scalar_one()
        item.quantity = quantity

        await self.db.flush()
        return item

    async def remove_item(self, item_id: int) -> None:
        result = await self.db.execute(
            select(CartItem).where(CartItem.id == item_id)
        )
        item = result.scalar_one()
        await self.db.delete(item)
        await self.db.flush()