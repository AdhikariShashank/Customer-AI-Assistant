
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product


class OrderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_user(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        count_result = await self.db.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.user_id == user_id)
        )
        total = count_result.scalar_one()

        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_by_user_and_id(
        self,
        user_id: int,
        order_id: int,
    ) -> Order | None:
        stmt = (
            select(Order)
            .where(
                Order.id == order_id,
                Order.user_id == user_id,
            )
            .options(selectinload(Order.items))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def place_order_from_cart(
        self,
        user_id: int,
    ) -> Order:
        try:
            # Lock the active cart to serialize checkout attempts.
            result = await self.db.execute(
                select(Cart)
                .where(
                    Cart.user_id == user_id,
                    Cart.status == "ACTIVE",
                )
                .with_for_update()
            )
            cart = result.scalar_one_or_none()

            if cart is None:
                raise AppException(
                    code="CART_NOT_FOUND",
                    message="No active cart was found",
                )

            # Load cart items after acquiring the cart lock.
            result = await self.db.execute(
                select(CartItem)
                .where(CartItem.cart_id == cart.id)
                .order_by(CartItem.id)
            )
            cart_items = list(result.scalars().all())

            if not cart_items:
                raise AppException(
                    code="CART_EMPTY",
                    message="Cannot place an order with an empty cart",
                )

            product_ids = sorted({
                item.product_id for item in cart_items
            })

            # Lock products in a consistent order to reduce deadlocks.
            result = await self.db.execute(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
            )
            products = {
                product.id: product
                for product in result.scalars().all()
            }

            order_lines = []
            total_amount = 0

            for item in cart_items:
                product = products.get(item.product_id)

                if product is None or not product.is_active:
                    raise AppException(
                        code="PRODUCT_NOT_FOUND",
                        message=(
                            f"Product {item.product_id} is unavailable"
                        ),
                    )

                if product.stock < item.quantity:
                    raise AppException(
                        code="PRODUCT_OUT_OF_STOCK",
                        message=(
                            f"Only {product.stock} units of "
                            f"{product.name} are available"
                        ),
                    )

                # Use the current price, not the old cart price.
                unit_price = product.price
                subtotal = unit_price * item.quantity

                order_lines.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                })

                total_amount += subtotal

            order = Order(
                user_id=user_id,
                status="PLACED",
                total_amount=total_amount,
            )
            self.db.add(order)
            await self.db.flush()

            for line in order_lines:
                self.db.add(
                    OrderItem(
                        order_id=order.id,
                        **line,
                    )
                )

                products[line["product_id"]].stock -= line["quantity"]

            cart.status = "CHECKED_OUT"

            await self.db.flush()
            order_id = order.id

            # This repository owns the checkout transaction.
            await self.db.commit()

            return await self.get_by_user_and_id(
                user_id=user_id,
                order_id=order_id,
            )

        except Exception:
            await self.db.rollback()
            raise

    async def cancel_order(
        self,
        user_id: int,
        order_id: int,
    ) -> Order:
        try:
            result = await self.db.execute(
                select(Order)
                .where(
                    Order.id == order_id,
                    Order.user_id == user_id,
                )
                .with_for_update()
            )
            order = result.scalar_one_or_none()

            if order is None:
                raise AppException(
                    code="ORDER_NOT_FOUND",
                    message=f"Order {order_id} was not found",
                )

            if order.status != "PLACED":
                raise AppException(
                    code="ORDER_CANNOT_BE_CANCELLED",
                    message="Only placed orders can be cancelled",
                )

            result = await self.db.execute(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(OrderItem.product_id)
            )
            order_items = list(result.scalars().all())

            product_ids = sorted({
                item.product_id for item in order_items
            })

            if product_ids:
                result = await self.db.execute(
                    select(Product)
                    .where(Product.id.in_(product_ids))
                    .order_by(Product.id)
                    .with_for_update()
                )
                products = {
                    product.id: product
                    for product in result.scalars().all()
                }

                for item in order_items:
                    product = products.get(item.product_id)
                    if product is not None:
                        product.stock += item.quantity

            order.status = "CANCELLED"

            await self.db.commit()

            return await self.get_by_user_and_id(
                user_id=user_id,
                order_id=order_id,
            )

        except Exception:
            await self.db.rollback()
            raise