import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine
from app.models.user import User
from app.models.user_memory import UserMemory
from app.repositories.semantic_memory import SemanticMemoryRepository


@pytest.mark.asyncio
async def test_semantic_memory_repository():

    async with AsyncSession(engine, expire_on_commit=False) as db:

        try:
            result = await db.execute(
                select(User).order_by(User.id).limit(1)
            )
            user = result.scalar_one_or_none()

            if user is None:
                pytest.skip("No existing user available for test")

            repo = SemanticMemoryRepository(db)

            memory = await repo.create(
                user_id=user.id,
                category="preference",
                key="phase2_test_brand",
                value={"brand": "Samsung"},
                confidence=1.0,
                source="test",
            )

            assert memory.id is not None

            saved = await repo.get_by_key(
                user_id=user.id,
                category="preference",
                key="phase2_test_brand",
            )

            assert saved is not None
            assert saved.value["brand"] == "Samsung"

            updated = await repo.update(
                user_id=user.id,
                memory_id=memory.id,
                value={"brand": "Apple"},
                confidence=0.9,
                source="test",
            )

            assert updated is not None
            assert updated.value["brand"] == "Apple"

            active_memories = await repo.list_active(
                user_id=user.id
            )

            assert any(
                item.id == memory.id
                for item in active_memories
            )

            deactivated = await repo.deactivate(
                user_id=user.id,
                memory_id=memory.id,
            )

            assert deactivated is not None
            assert deactivated.is_active is False

            active_memories = await repo.list_active(
                user_id=user.id
            )

            assert all(
                item.id != memory.id
                for item in active_memories
            )

        finally:
            await db.rollback()