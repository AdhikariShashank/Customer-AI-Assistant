from decimal import Decimal

from app.core.exceptions import AppException
from app.repositories.product import ProductRepository


class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    async def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
        offset: int = 0,
    ):
        if (
            min_price is not None
            and max_price is not None
            and min_price > max_price
        ):
            raise AppException(
                code="INVALID_PRICE_RANGE",
                message="Minimum price cannot exceed maximum price",
            )

        return await self.repository.search_products(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
            offset=offset,
        )

    async def get_product(self, product_id: int):
        product = await self.repository.get_by_id(product_id)

        if product is None:
            raise AppException(
                code="PRODUCT_NOT_FOUND",
                message=f"Product with id {product_id} was not found",
            )

        return product