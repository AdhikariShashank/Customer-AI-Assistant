"""Database setup.

Two engines on purpose (kept simple for teaching):
  * ASYNC  -> used by FastAPI routers (async endpoints).
  * SYNC   -> used by the LangGraph agent tools (@tool functions are plain sync functions,
              exactly like the todo-agent reference, so a normal blocking session is easiest).
Both point at the SAME Postgres database.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs

from .config import get_settings

settings = get_settings()

# --- async (FastAPI) ---
engine = create_async_engine(url=settings.database_url, echo=False)
AsyncLocalSession = async_sessionmaker(bind=engine, expire_on_commit=False)

# --- sync (agent tools) ---
sync_engine = create_engine(settings.sync_database_url, echo=False)
SessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency: yields one async session per request."""
    async with AsyncLocalSession() as session:
        yield session

 
