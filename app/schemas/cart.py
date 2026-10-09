from fastapi import APIRouter, Depends, Query

from app.schemas.common import SuccessResponse
from app.schemas.product import (
    ProductListResponse,
    ProductResponse,
)
from app.services.product import ProductService


router = APIRouter(prefix="/api/v1/products", tags=["Products"])


@router.get(
    "",
    response_model=SuccessResponse[ProductListResponse],
)
async def search_products(
    query: str | None = Query(default=None),
    category: str | None = Query(default=None),
    min_price: float | None = Query(default=None, gt=0),
    max_price: float | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: ProductService = Depends(),
):
    products, total = await service.search_products(
        query=query,
        category=category,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        offset=offset,
    )

    return SuccessResponse(
        data=ProductListResponse(
            items=products,
            total=total,
        ),
        message="Products fetched successfully",
    )


@router.get(
    "/{product_id}",
    response_model=SuccessResponse[ProductResponse],
)
async def get_product(
    product_id: int,
    service: ProductService = Depends(),
):
    product = await service.get_product(product_id)

    return SuccessResponse(
        data=product,
        message="Product fetched successfully",
    )