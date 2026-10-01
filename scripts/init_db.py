"""Create all database tables. Run once before starting the API:  python -m scripts.init_db

(For teaching we use create_all; in a real project you'd use Alembic migrations.)"""
import asyncio

from app.db import engine, Base
from app import models  # noqa: F401  (import registers the tables on Base.metadata)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created.")


if __name__ == "__main__":
    asyncio.run(main())
