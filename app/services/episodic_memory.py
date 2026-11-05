from datetime import datetime, timezone
from typing import Any

from app.models.user_episode import UserEpisode
from app.repositories.episodic_memory import EpisodicMemoryRepository


class EpisodicMemoryService:

    def __init__(
        self,
        repository: EpisodicMemoryRepository,
    ):
        self.repository = repository

    async def record_event(
        self,
        *,
        user_id: int,
        event_type: str,
        description: str,
        episode_metadata: dict[str, Any] | None = None,
        source_thread_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> UserEpisode:

        if user_id <= 0:
            raise ValueError("user_id must be positive")

        event_type = event_type.strip()
        description = description.strip()

        if not event_type or len(event_type) > 100:
            raise ValueError("event_type must be 1-100 characters")

        if not description:
            raise ValueError("description cannot be empty")

        if episode_metadata is not None and not isinstance(
            episode_metadata, dict
        ):
            raise ValueError("episode_metadata must be a dictionary")

        if occurred_at is not None:
            if (
                occurred_at.tzinfo is None
                or occurred_at.utcoffset() is None
            ):
                raise ValueError("occurred_at must be timezone-aware")

        return await self.repository.create(
            user_id=user_id,
            event_type=event_type,
            description=description,
            episode_metadata=episode_metadata,
            source_thread_id=source_thread_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )

    async def get_event(
        self,
        *,
        user_id: int,
        episode_id: int,
    ) -> UserEpisode | None:

        if user_id <= 0 or episode_id <= 0:
            raise ValueError("IDs must be positive")

        return await self.repository.get_by_id(
            user_id=user_id,
            episode_id=episode_id,
        )

    async def get_recent_events(
        self,
        *,
        user_id: int,
        limit: int = 20,
    ) -> list[UserEpisode]:

        if user_id <= 0:
            raise ValueError("user_id must be positive")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        return await self.repository.list_recent(
            user_id=user_id,
            limit=limit,
        )

    async def get_events_by_type(
        self,
        *,
        user_id: int,
        event_type: str,
        limit: int = 20,
    ) -> list[UserEpisode]:

        if user_id <= 0:
            raise ValueError("user_id must be positive")

        event_type = event_type.strip()

        if not event_type or len(event_type) > 100:
            raise ValueError("Invalid event_type")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        return await self.repository.list_by_event_type(
            user_id=user_id,
            event_type=event_type,
            limit=limit,
        )