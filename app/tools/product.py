import json
import logging
from decimal import Decimal
from typing import AsyncContextManager, Callable

from langchain.tools import tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.product import ProductService

logger = logging.getLogger(__name__)


class GetProductInput(BaseModel):
    """Validated input for retrieving a single product."""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(
        gt=0,
        description="The unique ID of the product to retrieve.",
    )


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
        """Search active catalog products by keyword, category, or price."""

        logger.info(
            "Tool started: search_products | query=%s category=%s "
            "min_price=%s max_price=%s limit=%s offset=%s",
            query,
            category,
            min_price,
            max_price,
            limit,
            offset,
        )

        try:
            # Validate input
            filters = ProductSearchInput(
                query=query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                limit=limit,
                offset=offset,
            )

            logger.debug(
                "search_products: input validation successful"
            )

            # Execute service operation
            async with product_service_context() as service:
                logger.debug(
                    "search_products: product service context opened"
                )

                products, total = await service.search_products(
                    query=filters.query,
                    category=filters.category,
                    min_price=filters.min_price,
                    max_price=filters.max_price,
                    limit=filters.limit,
                    offset=filters.offset,
                )

                logger.info(
                    "search_products: service returned %d products "
                    "out of %d total matches",
                    len(products),
                    total,
                )

                # Convert ORM objects while the session is open
                product_items = [
                    {
                        "id": product.id,
                        "name": product.name,
                        "category": product.category,
                        "description": product.description,
                        "price": str(product.price),
                        "stock": product.stock,
                    }
                    for product in products
                ]

            logger.debug(
                "search_products: product data serialization completed"
            )

            result = {
                "ok": True,
                "filters": {
                    "query": filters.query,
                    "category": filters.category,
                    "min_price": (
                        str(filters.min_price)
                        if filters.min_price is not None
                        else None
                    ),
                    "max_price": (
                        str(filters.max_price)
                        if filters.max_price is not None
                        else None
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

            output = json.dumps(result, ensure_ascii=False)

            logger.info(
                "Tool completed: search_products | returned=%d "
                "total=%d has_more=%s",
                len(product_items),
                total,
                result["pagination"]["has_more"],
            )

            return output

        except Exception:
            logger.exception(
                "Tool failed: search_products"
            )

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

    @tool("get_product", args_schema=GetProductInput)
    async def get_product(product_id: int) -> str:
        """Retrieve a single product by its unique ID."""

        logger.info(
            "Tool started: get_product | product_id=%s",
            product_id,
        )

        try:
            # Validate input
            filters = GetProductInput(product_id=product_id)

            logger.debug(
                "get_product: input validation successful"
            )

            # Retrieve product
            async with product_service_context() as service:
                logger.debug(
                    "get_product: product service context opened"
                )

                product = await service.get_product(
                    filters.product_id
                )

                if product is None:
                    logger.warning(
                        "get_product: product not found | product_id=%s",
                        filters.product_id,
                    )

                    return json.dumps({
                        "ok": False,
                        "error": {
                            "code": "PRODUCT_NOT_FOUND",
                            "message": (
                                f"Product with ID {filters.product_id} "
                                "was not found."
                            ),
                        },
                    })

                # Convert ORM object while the session is open
                product_data = {
                    "id": product.id,
                    "name": product.name,
                    "category": product.category,
                    "description": product.description,
                    "price": str(product.price),
                    "stock": product.stock,
                }

            logger.info(
                "get_product: product retrieved successfully | "
                "product_id=%s",
                filters.product_id,
            )

            output = json.dumps({
                "ok": True,
                "product": product_data,
            }, ensure_ascii=False)

            logger.info(
                "Tool completed: get_product | product_id=%s",
                filters.product_id,
            )

            return output

        except Exception:
            logger.exception(
                "Tool failed: get_product | product_id=%s",
                product_id,
            )

            return json.dumps({
                "ok": False,
                "error": {
                    "code": "PRODUCT_RETRIEVAL_UNAVAILABLE",
                    "message": (
                        "Product details are temporarily unavailable. "
                        "Please try again later."
                    ),
                },
            })

    logger.info(
        "Product tools initialized: search_products, get_product"
    )

    return [search_products, get_product]
