from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine
from app import models
from app.models.user import User
from app.repositories.episodic_memory import EpisodicMemoryRepository


@pytest.mark.asyncio
async def test_episodic_memory_repository():

    async with AsyncSession(engine, expire_on_commit=False) as db:
        try:
            result = await db.execute(
                select(User).order_by(User.id).limit(1)
            )
            user = result.scalar_one_or_none()

            if user is None:
                pytest.skip("No existing user available for test")

            repo = EpisodicMemoryRepository(db)

            now = datetime.now(timezone.utc)

            # 1. Create an older episode
            older = await repo.create(
                user_id=user.id,
                event_type="delivery_issue",
                description="User reported delayed delivery",
                episode_metadata={"order_id": 101},
                occurred_at=now - timedelta(days=2),
            )

            # 2. Create a newer episode
            newer = await repo.create(
                user_id=user.id,
                event_type="refund_request",
                description="User requested a refund",
                episode_metadata={"order_id": 101},
                occurred_at=now,
            )

            assert older.id is not None
            assert newer.id is not None

            # 3. Retrieve an episode by ID
            saved = await repo.get_by_id(
                user_id=user.id,
                episode_id=older.id,
            )

            assert saved is not None
            assert saved.event_type == "delivery_issue"
            assert saved.episode_metadata["order_id"] == 101

            # 4. Retrieve recent episodes
            recent = await repo.list_recent(
                user_id=user.id,
                limit=20,
            )

            ids = [episode.id for episode in recent]

            assert newer.id in ids
            assert older.id in ids
            assert ids.index(newer.id) < ids.index(older.id)

            # 5. Filter by event type
            delivery_episodes = await repo.list_by_event_type(
                user_id=user.id,
                event_type="delivery_issue",
            )

            assert any(
                episode.id == older.id
                for episode in delivery_episodes
            )

            assert all(
                episode.event_type == "delivery_issue"
                for episode in delivery_episodes
            )

            # 6. Verify user isolation
            other_user_id = -1

            inaccessible = await repo.get_by_id(
                user_id=other_user_id,
                episode_id=older.id,
            )

            assert inaccessible is None

            print("\nEpisodic memory repository tests passed.")

        finally:
            await db.rollback()