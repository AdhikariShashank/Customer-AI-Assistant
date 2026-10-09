
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.repositories.product import ProductRepository
from app.repositories.cart import CartRepository
from app.repositories.order import OrderRepository
from app.services.product import ProductService
from app.services.cart import CartService
from app.services.order import OrderService


def get_product_service(
    db: AsyncSession = Depends(get_db),
) -> ProductService:
    return ProductService(
        repository=ProductRepository(db)
    )


def get_cart_service(
    db: AsyncSession = Depends(get_db),
) -> CartService:
    return CartService(
        cart_repository=CartRepository(db),
        product_repository=ProductRepository(db),
    )


def get_order_service(
    db: AsyncSession = Depends(get_db),
) -> OrderService:
    return OrderService(
        repository=OrderRepository(db)
    )