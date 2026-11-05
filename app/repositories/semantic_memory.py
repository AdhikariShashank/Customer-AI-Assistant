from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory


class SemanticMemoryRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        category: str,
        key: str,
        value: dict[str, Any],
        confidence: float = 1.0,
        source: str = "conversation",
        source_thread_id: str | None = None,
    ) -> UserMemory:

        memory = UserMemory(
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            confidence=confidence,
            source=source,
            source_thread_id=source_thread_id,
            is_active=True,
        )

        self.db.add(memory)
        await self.db.flush()

        return memory

    async def get_by_key(
        self,
        *,
        user_id: int,
        category: str,
        key: str,
    ) -> UserMemory | None:

        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.category == category,
            UserMemory.key == key,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(
        self,
        *,
        user_id: int,
        limit: int = 50,
    ) -> list[UserMemory]:

        stmt = (
            select(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
            )
            .order_by(
                UserMemory.updated_at.desc(),
                UserMemory.id.desc(),
            )
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        *,
        user_id: int,
        memory_id: int,
        value: dict[str, Any],
        confidence: float,
        source: str,
        source_thread_id: str | None = None,
    ) -> UserMemory | None:

        stmt = (
            select(UserMemory)
            .where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
            )
            .with_for_update()
        )

        result = await self.db.execute(stmt)
        memory = result.scalar_one_or_none()

        if memory is None:
            return None

        memory.value = value
        memory.confidence = confidence
        memory.source = source
        memory.source_thread_id = source_thread_id
        memory.is_active = True

        await self.db.flush()
        return memory


    async def deactivate(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> UserMemory | None:

        stmt = (
            select(UserMemory)
            .where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
            )
            .with_for_update()
        )

        result = await self.db.execute(stmt)
        memory = result.scalar_one_or_none()

        if memory is None:
            return None

        memory.is_active = False

        await self.db.flush()
        return memory