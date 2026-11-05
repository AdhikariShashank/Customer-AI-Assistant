import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.db import engine
from app.models.user import User
from app.repositories.semantic_memory import SemanticMemoryRepository
from app.services.semantic_memory import SemanticMemoryService


@pytest.mark.asyncio
async def test_semantic_memory_service():

    async with AsyncSession(engine, expire_on_commit=False) as db:
        try:
            result = await db.execute(
                select(User).order_by(User.id).limit(1)
            )
            user = result.scalar_one_or_none()

            if user is None:
                pytest.skip("No existing user available")

            repository = SemanticMemoryRepository(db)
            service = SemanticMemoryService(repository)

            # 1. Create memory
            memory = await service.remember(
                user_id=user.id,
                category="preference",
                key="phase3_test_phone_brand",
                value={"brand": "Samsung"},
                confidence=0.95,
            )

            assert memory.id is not None
            original_id = memory.id

            # 2. Same memory should not create a duplicate
            same = await service.remember(
                user_id=user.id,
                category="preference",
                key="phase3_test_phone_brand",
                value={"brand": "Samsung"},
                confidence=0.95,
            )

            assert same.id == original_id

            # 3. Change preference
            updated = await service.remember(
                user_id=user.id,
                category="preference",
                key="phase3_test_phone_brand",
                value={"brand": "Apple"},
                confidence=0.98,
            )

            assert updated.id == original_id
            assert updated.value["brand"] == "Apple"

            # 4. Forget memory
            forgotten = await service.forget(
                user_id=user.id,
                category="preference",
                key="phase3_test_phone_brand",
            )

            assert forgotten is True

            active = await service.get_active_memories(
                user_id=user.id
            )

            assert all(m.id != original_id for m in active)

            # 5. Reactivate memory
            reactivated = await service.remember(
                user_id=user.id,
                category="preference",
                key="phase3_test_phone_brand",
                value={"brand": "Samsung"},
                confidence=0.95,
            )

            assert reactivated.id == original_id
            assert reactivated.is_active is True

            # 6. Cross-user isolation
            other_memories = await service.get_active_memories(
                user_id=999999999
            )

            assert all(
                m.id != original_id
                for m in other_memories
            )

            # 7. Invalid confidence
            with pytest.raises(ValueError):
                await service.remember(
                    user_id=user.id,
                    category="preference",
                    key="invalid_confidence",
                    value={"brand": "Samsung"},
                    confidence=1.5,
                )

            print("\nSemanticMemoryService tests passed.")

        finally:
            await db.rollback()