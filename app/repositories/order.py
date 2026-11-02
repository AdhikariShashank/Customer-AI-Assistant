
from decimal import Decimal

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

    async def get_checkout_facts(
        self,
        user_id: int,
    ) -> dict | None:
        """
        Build trusted checkout facts and a cart snapshot.

        This is a preflight read used by governance.
        Final validation must happen during actual checkout.
        """

        result = await self.db.execute(
            select(Cart).where(
                Cart.user_id == user_id,
                Cart.status == "ACTIVE",
            )
        )
        cart = result.scalar_one_or_none()

        if cart is None:
            return None

        result = await self.db.execute(
            select(CartItem)
            .where(CartItem.cart_id == cart.id)
            .order_by(CartItem.id)
        )
        cart_items = list(result.scalars().all())

        if not cart_items:
            return {
                "cart_id": cart.id,
                "order_total": Decimal("0.00"),
                "currency": "INR",
                "cart_snapshot": {
                    "cart_id": cart.id,
                    "items": [],
                    "total_amount": "0.00",
                    "currency": "INR",
                },
            }

        product_ids = sorted({
            item.product_id for item in cart_items
        })

        result = await self.db.execute(
            select(Product).where(
                Product.id.in_(product_ids)
            )
        )

        products = {
            product.id: product
            for product in result.scalars().all()
        }

        if any(
            item.product_id not in products
            or not products[item.product_id].is_active
            for item in cart_items
        ):
            return None

        total = Decimal("0.00")
        snapshot_items = []

        for item in cart_items:
            product = products[item.product_id]

            unit_price = Decimal(str(product.price))
            subtotal = unit_price * item.quantity

            total += subtotal

            snapshot_items.append({
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": str(unit_price),
                "subtotal": str(subtotal),
            })

        return {
            "cart_id": cart.id,
            "order_total": total,
            "currency": "INR",
            "cart_snapshot": {
                "cart_id": cart.id,
                "items": snapshot_items,
                "total_amount": str(total),
                "currency": "INR",
            },
        }

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

    @staticmethod
    def _build_snapshot(
        cart_id: int,
        cart_items: list[CartItem],
        products: dict[int, Product],
    ) -> dict:
        """
        Build a normalized snapshot using current locked product prices.
        """

        total = Decimal("0.00")
        snapshot_items = []

        for item in cart_items:
            product = products.get(item.product_id)

            if product is None or not product.is_active:
                raise AppException(
                    code="PRODUCT_NOT_FOUND",
                    message=(
                        f"Product {item.product_id} is unavailable"
                    ),
                )

            unit_price = Decimal(str(product.price))
            subtotal = unit_price * item.quantity

            total += subtotal

            snapshot_items.append({
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": str(unit_price),
                "subtotal": str(subtotal),
            })

        return {
            "cart_id": cart_id,
            "items": snapshot_items,
            "total_amount": str(total),
            "currency": "INR",
        }

    @staticmethod
    def _validate_expected_snapshot(
        actual_snapshot: dict,
        expected_snapshot: dict,
    ) -> None:
        """
        Ensure the current cart matches the approved cart snapshot.
        """

        if actual_snapshot != expected_snapshot:
            raise AppException(
                code="APPROVED_CART_CHANGED",
                message=(
                    "The cart or product prices have changed since "
                    "approval. A new approval is required."
                ),
            )

    async def place_order_from_cart(
        self,
        user_id: int,
        expected_snapshot: dict | None = None,
    ) -> Order:
        """
        Place an order using the authenticated user's active cart.

        If expected_snapshot is provided, checkout is allowed only
        when the current cart matches the approved snapshot.

        Transaction ownership belongs to the calling service/context.
        This repository method flushes but never commits or rolls back.
        """

        # 1. Lock the active cart.
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

        # 2. Lock cart items.
        result = await self.db.execute(
            select(CartItem)
            .where(CartItem.cart_id == cart.id)
            .order_by(CartItem.id)
            .with_for_update()
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

        # 3. Lock products in a consistent order.
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

        # 4. Validate product availability and stock.
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

        # 5. Recalculate the snapshot using locked, current data.
        current_snapshot = self._build_snapshot(
            cart_id=cart.id,
            cart_items=cart_items,
            products=products,
        )

        # 6. Compare against the administrator-approved snapshot.
        if expected_snapshot is not None:
            self._validate_expected_snapshot(
                actual_snapshot=current_snapshot,
                expected_snapshot=expected_snapshot,
            )

        # 7. Build order lines.
        order_lines = []
        total_amount = Decimal("0.00")

        for item in cart_items:
            product = products[item.product_id]

            unit_price = Decimal(str(product.price))
            subtotal = unit_price * item.quantity

            order_lines.append({
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
            })

            total_amount += subtotal

        # 8. Create order.
        order = Order(
            user_id=user_id,
            status="PLACED",
            total_amount=total_amount,
        )

        self.db.add(order)
        await self.db.flush()

        # 9. Create order items and update stock.
        for line in order_lines:
            self.db.add(
                OrderItem(
                    order_id=order.id,
                    **line,
                )
            )

            products[line["product_id"]].stock -= line["quantity"]

        # 10. Mark cart as checked out.
        cart.status = "CHECKED_OUT"

        await self.db.flush()

        # 11. Return the created order.
        created_order = await self.get_by_user_and_id(
            user_id=user_id,
            order_id=order.id,
        )

        if created_order is None:
            raise AppException(
                code="ORDER_CREATION_FAILED",
                message="Unable to retrieve the created order",
            )

        return created_order

    async def cancel_order(
        self,
        user_id: int,
        order_id: int,
    ) -> Order:
        """
        Cancel an order and restore its inventory.

        Transaction ownership belongs to the calling service/context.
        """

        # 1. Lock the order.
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

        # 2. Load order items.
        result = await self.db.execute(
            select(OrderItem)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.product_id)
        )

        order_items = list(result.scalars().all())

        product_ids = sorted({
            item.product_id for item in order_items
        })

        # 3. Lock products in a consistent order.
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

            # 4. Restore inventory.
            for item in order_items:
                product = products.get(item.product_id)

                if product is not None:
                    product.stock += item.quantity

        # 5. Update order status.
        order.status = "CANCELLED"

        await self.db.flush()

        cancelled_order = await self.get_by_user_and_id(
            user_id=user_id,
            order_id=order_id,
        )

        if cancelled_order is None:
            raise AppException(
                code="ORDER_CANCELLATION_FAILED",
                message="Unable to retrieve the cancelled order",
            )

        return cancelled_order
