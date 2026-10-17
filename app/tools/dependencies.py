
from contextlib import asynccontextmanager

from app.db import AsyncLocalSession
from app.repositories.product import ProductRepository
from app.services.product import ProductService


@asynccontextmanager
async def product_service_context():
    async with AsyncLocalSession() as db:
        repository = ProductRepository(db)

        service = ProductService(repository)

        yield service
