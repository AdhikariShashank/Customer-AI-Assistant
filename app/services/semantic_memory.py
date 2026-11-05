from typing import Any

from app.models.user_memory import UserMemory
from app.repositories.semantic_memory import SemanticMemoryRepository


class SemanticMemoryService:

    def __init__(
        self,
        repository: SemanticMemoryRepository,
    ):
        self.repository = repository

    async def remember(
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

        # 1. Validate structured input
        if user_id <= 0:
            raise ValueError("user_id must be positive")

        if not category.strip():
            raise ValueError("category cannot be empty")

        if not key.strip():
            raise ValueError("key cannot be empty")

        if not isinstance(value, dict) or not value:
            raise ValueError("value must be a non-empty dictionary")

        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        # 2. Find existing memory
        existing = await self.repository.get_by_key(
            user_id=user_id,
            category=category,
            key=key,
        )

        # 3. Create new memory
        if existing is None:
            return await self.repository.create(
                user_id=user_id,
                category=category,
                key=key,
                value=value,
                confidence=confidence,
                source=source,
                source_thread_id=source_thread_id,
            )

        # 4. Avoid unnecessary updates
        if (
            existing.is_active
            and existing.value == value
            and existing.confidence == confidence
            and existing.source == source
            and existing.source_thread_id == source_thread_id
        ):
            return existing

        # 5. Update existing memory
        updated = await self.repository.update(
            user_id=user_id,
            memory_id=existing.id,
            value=value,
            confidence=confidence,
            source=source,
            source_thread_id=source_thread_id,
        )

        if updated is None:
            raise RuntimeError("Memory disappeared during update")

        return updated

    async def get_active_memories(
        self,
        *,
        user_id: int,
        limit: int = 50,
    ) -> list[UserMemory]:

        if user_id <= 0:
            raise ValueError("user_id must be positive")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        return await self.repository.list_active(
            user_id=user_id,
            limit=limit,
        )

    async def forget(
        self,
        *,
        user_id: int,
        category: str,
        key: str,
    ) -> bool:

        if user_id <= 0:
            raise ValueError("user_id must be positive")

        existing = await self.repository.get_by_key(
            user_id=user_id,
            category=category,
            key=key,
        )

        if existing is None or not existing.is_active:
            return False

        deactivated = await self.repository.deactivate(
            user_id=user_id,
            memory_id=existing.id,
        )

        return deactivated is not None