from app.core.exceptions import AppException
from app.repositories.order import OrderRepository


class OrderService:
    def __init__(self, repository: OrderRepository):
        self.repository = repository

    async def list_orders(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ):
        return await self.repository.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def get_order(self, user_id: int, order_id: int):
        order = await self.repository.get_by_user_and_id(
            user_id=user_id,
            order_id=order_id,
        )

        if order is None:
            raise AppException(
                code="ORDER_NOT_FOUND",
                message=f"Order with id {order_id} was not found",
            )

        return order

    async def place_order(self, user_id: int):
        # The repository must perform checkout atomically:
        # validate cart, verify stock, snapshot prices,
        # create order/items, decrement stock and close cart.
        order = await self.repository.place_order_from_cart(
            user_id=user_id,
        )

        return order

    async def cancel_order(self, user_id: int, order_id: int):
        order = await self.repository.get_by_user_and_id(
            user_id=user_id,
            order_id=order_id,
        )

        if order is None:
            raise AppException(
                code="ORDER_NOT_FOUND",
                message=f"Order with id {order_id} was not found",
            )

        if order.status != "PLACED":
            raise AppException(
                code="ORDER_CANNOT_BE_CANCELLED",
                message="Only placed orders can be cancelled",
            )

        return await self.repository.cancel_order(
            user_id=user_id,
            order_id=order_id,
        )