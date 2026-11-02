from contextlib import asynccontextmanager

from app.db import AsyncLocalSession
from app.repositories.agent_execution import AgentExecutionRepository
from app.repositories.order import OrderRepository
from app.repositories.product import ProductRepository
from app.repositories.cart import CartRepository
from app.services.agent_execution import AgentExecutionService
from app.services.order import OrderService
from app.services.product import ProductService
from app.services.cart import CartService
from app.repositories.approval import ApprovalRepository
from app.services.approval import ApprovalService


@asynccontextmanager
async def execution_service_context():
    async with AsyncLocalSession() as db:
        try:
            repository = AgentExecutionRepository(db)
            service = AgentExecutionService(repository)

            yield service

            await db.commit()

        except Exception:
            await db.rollback()
            raise

from contextlib import asynccontextmanager

from app.planner.operations import OperationSpec
from app.repositories.approval import ApprovalRepository
from app.repositories.agent_execution import AgentExecutionRepository
from app.services.approval import ApprovalService


@asynccontextmanager
async def approval_service_context(
    operation_registry: dict[str, OperationSpec],
):
    async with AsyncLocalSession() as db:
        try:
            approval_repository = ApprovalRepository(db)
            execution_repository = AgentExecutionRepository(db)

            service = ApprovalService(
                repository=approval_repository,
                execution_repository=execution_repository,
                operation_registry=operation_registry,
            )

            yield service
            await db.commit()

        except Exception:
            await db.rollback()
            raise


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


@asynccontextmanager
async def order_service_context():
    async with AsyncLocalSession() as db:
        try:
            repository = OrderRepository(db)
            service = OrderService(repository)

            yield service

            await db.commit()

        except Exception:
            await db.rollback()
            raise