from contextlib import asynccontextmanager

from app.db import AsyncLocalSession
from app.repositories.product import ProductRepository
from app.repositories.cart import CartRepository
from app.services.product import ProductService
from app.services.cart import CartService


@asynccontextmanager
async def product_service_context():
    async with AsyncLocalSession() as db:
        repository = ProductRepository(db)
        service = ProductService(repository)

        yield service


@asynccontextmanager
async def cart_service_context():
    async with AsyncLocalSession() as db:
        try:
            cart_repository = CartRepository(db)
            product_repository = ProductRepository(db)

            service = CartService(
                cart_repository=cart_repository,
                product_repository=product_repository,
            )

            yield service

            await db.commit()

        except Exception:
            await db.rollback()
            raise