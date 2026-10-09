
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class ProductRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, product_id: int) -> Product | None:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        filters = [Product.is_active.is_(True)]

        if query:
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(
                    Product.name.ilike(pattern),
                    Product.description.ilike(pattern),
                )
            )

        if category:
            filters.append(
                Product.category.ilike(category.strip())
            )

        if min_price is not None:
            filters.append(Product.price >= min_price)

        if max_price is not None:
            filters.append(Product.price <= max_price)

        count_stmt = (
            select(func.count())
            .select_from(Product)
            .where(*filters)
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = (
            select(Product)
            .where(*filters)
            .order_by(Product.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        products = list(result.scalars().all())

        return products, total