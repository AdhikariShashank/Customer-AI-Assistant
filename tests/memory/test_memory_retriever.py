from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.memory.retriever import MemoryRetriever


@pytest.mark.asyncio
async def test_memory_retriever_filters_memories():

    semantic_service = AsyncMock()
    episodic_service = AsyncMock()

    semantic_service.get_active_memories.return_value = [
        SimpleNamespace(
            category="preference",
            key="preferred_phone_brand",
            value={"brand": "Samsung"},
        ),
        SimpleNamespace(
            category="constraint",
            key="phone_budget",
            value={"amount": 30000},
        ),
        SimpleNamespace(
            category="profile",
            key="preferred_language",
            value={"language": "English"},
        ),
    ]

    episodic_service.get_recent_events.return_value = [
        SimpleNamespace(
            event_type="delivery_issue",
            description="Order 101 was delayed",
        ),
        SimpleNamespace(
            event_type="refund_request",
            description="Refund requested for order 101",
        ),
    ]

    retriever = MemoryRetriever(
        semantic_service=semantic_service,
        episodic_service=episodic_service,
    )

    result = await retriever.retrieve(
        user_id=7,
        categories={"preference", "constraint"},
        event_types={"delivery_issue"},
    )

    assert len(result.semantic) == 2
    assert len(result.episodic) == 1

    assert {
        memory.key for memory in result.semantic
    } == {
        "preferred_phone_brand",
        "phone_budget",
    }

    assert result.episodic[0].event_type == "delivery_issue"

    semantic_service.get_active_memories.assert_awaited_once_with(
        user_id=7,
        limit=30,
    )

    episodic_service.get_recent_events.assert_awaited_once_with(
        user_id=7,
        limit=10,
    )


@pytest.mark.asyncio
async def test_memory_retriever_rejects_invalid_user():

    retriever = MemoryRetriever(
        semantic_service=AsyncMock(),
        episodic_service=AsyncMock(),
    )

    with pytest.raises(ValueError):
        await retriever.retrieve(user_id=0)