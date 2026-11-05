from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_episode import UserEpisode


class EpisodicMemoryRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        event_type: str,
        description: str,
        episode_metadata: dict[str, Any] | None = None,
        source_thread_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> UserEpisode:

        episode = UserEpisode(
            user_id=user_id,
            event_type=event_type,
            description=description,
            episode_metadata=episode_metadata or {},
            source_thread_id=source_thread_id,
            occurred_at=occurred_at,
        )

        self.db.add(episode)
        await self.db.flush()

        return episode

    async def get_by_id(
        self,
        *,
        user_id: int,
        episode_id: int,
    ) -> UserEpisode | None:

        stmt = select(UserEpisode).where(
            UserEpisode.id == episode_id,
            UserEpisode.user_id == user_id,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(
        self,
        *,
        user_id: int,
        limit: int = 20,
    ) -> list[UserEpisode]:

        stmt = (
            select(UserEpisode)
            .where(UserEpisode.user_id == user_id)
            .order_by(
                UserEpisode.occurred_at.desc().nulls_last(),
                UserEpisode.created_at.desc(),
                UserEpisode.id.desc(),
            )
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_event_type(
        self,
        *,
        user_id: int,
        event_type: str,
        limit: int = 20,
    ) -> list[UserEpisode]:

        stmt = (
            select(UserEpisode)
            .where(
                UserEpisode.user_id == user_id,
                UserEpisode.event_type == event_type,
            )
            .order_by(
                UserEpisode.occurred_at.desc().nulls_last(),
                UserEpisode.created_at.desc(),
                UserEpisode.id.desc(),
            )
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())