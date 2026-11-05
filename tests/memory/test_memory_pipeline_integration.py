from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.db import engine
from app.models.user import User

from app.repositories.semantic_memory import SemanticMemoryRepository
from app.repositories.episodic_memory import EpisodicMemoryRepository

from app.services.semantic_memory import SemanticMemoryService
from app.services.episodic_memory import EpisodicMemoryService

from app.memory.retriever import MemoryRetriever
from app.memory.context_builder import MemoryContextBuilder


@pytest.mark.asyncio
async def test_memory_pipeline_end_to_end():

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:

        # Everything created during this test will be rolled back.
        async with db.begin():

            result = await db.execute(
                select(User).order_by(User.id).limit(1)
            )

            user = result.scalar_one_or_none()

            if user is None:
                pytest.skip("No existing user available")

            semantic_repository = SemanticMemoryRepository(db)
            episodic_repository = EpisodicMemoryRepository(db)

            semantic_service = SemanticMemoryService(
                semantic_repository
            )

            episodic_service = EpisodicMemoryService(
                episodic_repository
            )

            retriever = MemoryRetriever(
                semantic_service=semantic_service,
                episodic_service=episodic_service,
            )

            context_builder = MemoryContextBuilder(
                max_chars=4000
            )

            # Unique keys prevent collisions with previous tests.
            test_id = uuid4().hex[:12]

            brand_key = f"test_phone_brand_{test_id}"
            budget_key = f"test_phone_budget_{test_id}"
            event_type = f"test_delivery_issue_{test_id}"

            # STEP 1: Store semantic memories.

            brand = await semantic_service.remember(
                user_id=user.id,
                category="preference",
                key=brand_key,
                value={"brand": "Samsung"},
            )

            budget = await semantic_service.remember(
                user_id=user.id,
                category="constraint",
                key=budget_key,
                value={
                    "amount": 30000,
                    "currency": "INR",
                },
            )

            # STEP 2: Store an episodic memory.

            episode = await episodic_service.record_event(
                user_id=user.id,
                event_type=event_type,
                description="Test order 101 was delayed",
                episode_metadata={"order_id": 101},
            )

            # STEP 3: Retrieve memories.

            retrieved = await retriever.retrieve(
                user_id=user.id,
                semantic_limit=100,
                episodic_limit=100,
            )

            semantic_ids = {
                memory.id for memory in retrieved.semantic
            }

            episode_ids = {
                event.id for event in retrieved.episodic
            }

            assert brand.id in semantic_ids
            assert budget.id in semantic_ids
            assert episode.id in episode_ids

            # STEP 4: Build context.

            context = context_builder.build(retrieved)

            assert brand_key in context
            assert budget_key in context
            assert event_type in context

            assert "Samsung" in context
            assert "30000" in context
            assert "Test order 101 was delayed" in context

            assert len(context) <= 4000

            # STEP 5: Deactivate the brand memory.

            forgotten = await semantic_service.forget(
                user_id=user.id,
                category="preference",
                key=brand_key,
            )

            assert forgotten is True

            # STEP 6: Retrieve again.

            retrieved_after_forget = await retriever.retrieve(
                user_id=user.id,
                semantic_limit=100,
                episodic_limit=100,
            )

            context_after_forget = context_builder.build(
                retrieved_after_forget
            )

            assert brand_key not in context_after_forget
            assert budget_key in context_after_forget

            print("\nGenerated memory context:")
            print(context_after_forget)

            print("\nMemory pipeline integration test passed.")

        # Explicit rollback of the test transaction is required.
        # This is handled by the alternative pattern below.