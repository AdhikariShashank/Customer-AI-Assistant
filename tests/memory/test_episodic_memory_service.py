from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.db import engine
from app.models.user import User
from app.repositories.episodic_memory import EpisodicMemoryRepository
from app.services.episodic_memory import EpisodicMemoryService


@pytest.mark.asyncio
async def test_episodic_memory_service():

    async with AsyncSession(engine, expire_on_commit=False) as db:
        try:
            result = await db.execute(
                select(User).order_by(User.id).limit(1)
            )
            user = result.scalar_one_or_none()

            if user is None:
                pytest.skip("No existing user available")

            repository = EpisodicMemoryRepository(db)
            service = EpisodicMemoryService(repository)

            # 1. Record an event
            episode = await service.record_event(
                user_id=user.id,
                event_type="delivery_issue",
                description="Customer reported delayed delivery",
                episode_metadata={"order_id": 101},
                occurred_at=datetime.now(timezone.utc),
            )

            assert episode.id is not None
            assert episode.event_type == "delivery_issue"

            # 2. Retrieve the event
            saved = await service.get_event(
                user_id=user.id,
                episode_id=episode.id,
            )

            assert saved is not None
            assert saved.episode_metadata["order_id"] == 101

            # 3. Retrieve recent events
            recent = await service.get_recent_events(
                user_id=user.id,
            )

            assert any(e.id == episode.id for e in recent)

            # 4. Filter by event type
            filtered = await service.get_events_by_type(
                user_id=user.id,
                event_type="delivery_issue",
            )

            assert any(e.id == episode.id for e in filtered)

            # 5. Verify user isolation
            inaccessible = await service.get_event(
                user_id=999999999,
                episode_id=episode.id,
            )

            assert inaccessible is None

            # 6. Validate empty description
            with pytest.raises(ValueError):
                await service.record_event(
                    user_id=user.id,
                    event_type="delivery_issue",
                    description="   ",
                )

            # 7. Validate timezone
            with pytest.raises(ValueError):
                await service.record_event(
                    user_id=user.id,
                    event_type="delivery_issue",
                    description="Invalid timestamp",
                    occurred_at=datetime(2026, 11, 5),
                )

            print("\nEpisodicMemoryService tests passed.")

        finally:
            await db.rollback()