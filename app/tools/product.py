
# app/tools/product.py

import json
import logging
from decimal import Decimal
from typing import AsyncContextManager, Callable

from langchain.tools import tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.product import ProductService

logger = logging.getLogger(__name__)


class ProductSearchInput(BaseModel):
    """Validated filters for searching the product catalog."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Product keywords, e.g. wireless keyboard.",
    )
    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Exact product category.",
    )
    min_price: Decimal | None = Field(default=None, gt=0)
    max_price: Decimal | None = Field(default=None, gt=0)
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_price_range(self):
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price cannot exceed max_price")
        return self


ProductServiceContextFactory = Callable[
    [], AsyncContextManager[ProductService]
]


def create_product_tools(
    product_service_context: ProductServiceContextFactory,
):
    """Create product tools using a fresh service/session scope."""

    @tool("search_products", args_schema=ProductSearchInput)
    async def search_products(
        query: str | None = None,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> str:
        """Search active catalog products by keyword, category, or price.

        Use for product discovery and comparison. Keyword matching
        uses the backend's existing substring search. Category
        matching uses case-insensitive exact matching.
        """

        filters = ProductSearchInput(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
            offset=offset,
        )

        try:
            async with product_service_context() as service:
                products, total = await service.search_products(
                    query=filters.query,
                    category=filters.category,
                    min_price=filters.min_price,
                    max_price=filters.max_price,
                    limit=filters.limit,
                    offset=filters.offset,
                )

            product_items = [
                {
                    "id": product.id,
                    "name": product.name,
                    "category": product.category,
                    "description": product.description,
                    "price": str(product.price),
                    # Change this attribute if your model uses
                    # a different stock field name.
                    "stock": product.stock,
                }
                for product in products
            ]

            result = {
                "ok": True,
                "filters": {
                    "query": filters.query,
                    "category": filters.category,
                    "min_price": (
                        str(filters.min_price)
                        if filters.min_price is not None else None
                    ),
                    "max_price": (
                        str(filters.max_price)
                        if filters.max_price is not None else None
                    ),
                },
                "products": product_items,
                "pagination": {
                    "limit": filters.limit,
                    "offset": filters.offset,
                    "total": total,
                    "returned": len(product_items),
                    "has_more": (
                        filters.offset + len(product_items) < total
                    ),
                },
            }
            return json.dumps(result, ensure_ascii=False)

        except Exception:
            logger.exception("Product search tool execution failed")
            return json.dumps({
                "ok": False,
                "error": {
                    "code": "PRODUCT_SEARCH_UNAVAILABLE",
                    "message": (
                        "Product search is temporarily unavailable. "
                        "Please try again later."
                    ),
                },
            })

    return [search_products]
