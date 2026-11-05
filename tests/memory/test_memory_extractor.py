
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.extractor import MemoryExtractor
from app.memory.schemas import MemoryExtractionResult


@pytest.mark.asyncio
async def test_memory_extractor_returns_structured_memories():

    expected = MemoryExtractionResult.model_validate(
        {
            "semantic_memories": [
                {
                    "category": "preference",
                    "key": "preferred_phone_brand",
                    "value": {"brand": "Samsung"},
                    "confidence": 0.95,
                }
            ],
            "episodic_memories": [],
        }
    )

    llm = MagicMock()
    llm.with_structured_output.return_value = MagicMock()

    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock(return_value=expected)

    result = await extractor.extract(
        customer_message="I prefer Samsung phones."
    )

    assert len(result.semantic_memories) == 1
    assert result.semantic_memories[0].key == "preferred_phone_brand"
    assert result.semantic_memories[0].value == {
        "brand": "Samsung"
    }

    llm.with_structured_output.assert_called_once_with(
        MemoryExtractionResult,
        method="function_calling",
    )

    extractor.chain.ainvoke.assert_awaited_once_with(
        {
            "customer_message": "I prefer Samsung phones."
        }
    )


@pytest.mark.asyncio
async def test_memory_extractor_empty_message():

    llm = MagicMock()
    llm.with_structured_output.return_value = MagicMock()

    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock()

    result = await extractor.extract(
        customer_message="   "
    )

    assert result.semantic_memories == []
    assert result.episodic_memories == []

    extractor.chain.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_extractor_validates_dict_result():

    llm = MagicMock()
    llm.with_structured_output.return_value = MagicMock()

    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock(
        return_value={
            "semantic_memories": [
                {
                    "category": "constraint",
                    "key": "phone_budget",
                    "value": {
                        "amount": 30000,
                        "currency": "INR",
                    },
                    "confidence": 0.95,
                }
            ],
            "episodic_memories": [],
        }
    )

    result = await extractor.extract(
        customer_message="My phone budget is INR 30000."
    )

    assert isinstance(result, MemoryExtractionResult)
    assert result.semantic_memories[0].category == "constraint"
    assert result.semantic_memories[0].value["amount"] == 30000
