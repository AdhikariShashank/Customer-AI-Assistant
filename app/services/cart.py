from app.core.exceptions import AppException
from app.repositories.cart import CartRepository
from app.repositories.product import ProductRepository


class CartService:
    def __init__(
        self,
        cart_repository: CartRepository,
        product_repository: ProductRepository,
    ):
        self.cart_repository = cart_repository
        self.product_repository = product_repository

    async def get_cart(self, user_id: int):
        cart = await self.cart_repository.get_active_cart(user_id)

        # A new customer may not have a cart yet.
        if cart is None:
            return await self.cart_repository.create_cart(user_id)

        return cart

    async def add_item(
        self,
        user_id: int,
        product_id: int,
        quantity: int,
    ):
        product = await self.product_repository.get_by_id(product_id)

        if product is None:
            raise AppException(
                code="PRODUCT_NOT_FOUND",
                message=f"Product with id {product_id} was not found",
            )

        if not product.is_active:
            raise AppException(
                code="PRODUCT_INACTIVE",
                message="This product is not available for purchase",
            )

        if quantity > product.stock:
            raise AppException(
                code="PRODUCT_OUT_OF_STOCK",
                message=f"Only {product.stock} units are available",
            )

        cart = await self.cart_repository.get_active_cart(user_id)

        if cart is None:
            cart = await self.cart_repository.create_cart(user_id)

        existing_item = await self.cart_repository.get_item(
            cart_id=cart.id,
            product_id=product_id,
        )

        new_quantity = quantity

        if existing_item is not None:
            new_quantity += existing_item.quantity

        if new_quantity > product.stock:
            raise AppException(
                code="PRODUCT_OUT_OF_STOCK",
                message=f"Only {product.stock} units are available",
            )

        if existing_item is not None:
            await self.cart_repository.update_item(
                item_id=existing_item.id,
                quantity=new_quantity,
            )
        else:
            await self.cart_repository.add_item(
                cart_id=cart.id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.price,
            )

        return await self.cart_repository.get_active_cart(user_id)

    async def update_item(
        self,
        user_id: int,
        item_id: int,
        quantity: int,
    ):
        item = await self.cart_repository.get_user_cart_item(
            user_id=user_id,
            item_id=item_id,
        )

        if item is None:
            raise AppException(
                code="CART_ITEM_NOT_FOUND",
                message="Cart item was not found",
            )

        product = await self.product_repository.get_by_id(
            item.product_id
        )

        if product is None or not product.is_active:
            raise AppException(
                code="PRODUCT_NOT_FOUND",
                message="Product is no longer available",
            )

        if quantity > product.stock:
            raise AppException(
                code="PRODUCT_OUT_OF_STOCK",
                message=f"Only {product.stock} units are available",
            )

        await self.cart_repository.update_item(
            item_id=item_id,
            quantity=quantity,
        )

        return await self.cart_repository.get_active_cart(user_id)

    async def remove_item(self, user_id: int, item_id: int):
        item = await self.cart_repository.get_user_cart_item(
            user_id=user_id,
            item_id=item_id,
        )

        if item is None:
            raise AppException(
                code="CART_ITEM_NOT_FOUND",
                message="Cart item was not found",
            )

        await self.cart_repository.remove_item(item_id)

        return await self.cart_repository.get_active_cart(user_id)