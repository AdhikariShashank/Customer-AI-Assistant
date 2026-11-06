
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.extractor import MemoryExtractor
from app.memory.schemas import (
    MemoryExtractionResult,
    MemoryOperation,
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_memory_extractor_returns_structured_memories():
    expected = MemoryExtractionResult.model_validate(
        {
            "semantic_operations": [
                {
                    "operation": "UPSERT",
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
    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock(return_value=expected)

    result = await extractor.extract(
        customer_message="I prefer Samsung phones."
    )

    assert len(result.semantic_operations) == 1

    operation = result.semantic_operations[0]

    assert operation.operation == MemoryOperation.UPSERT
    assert operation.key == "preferred_phone_brand"
    assert operation.value == {"brand": "Samsung"}

    llm.with_structured_output.assert_called_once_with(
        MemoryExtractionResult,
        method="function_calling",
    )

    extractor.chain.ainvoke.assert_awaited_once_with(
        {
            "customer_message": "I prefer Samsung phones.",
            "existing_memories": "[]",
        }
    )

    logger.info("test.memory_extractor_upsert_passed")


@pytest.mark.asyncio
async def test_memory_extractor_empty_message():
    llm = MagicMock()
    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock()

    result = await extractor.extract(
        customer_message="   "
    )

    assert result.semantic_operations == []
    assert result.episodic_memories == []

    extractor.chain.ainvoke.assert_not_awaited()

    logger.info("test.memory_extractor_empty_message_passed")


@pytest.mark.asyncio
async def test_memory_extractor_validates_dict_result():
    llm = MagicMock()
    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock(
        return_value={
            "semantic_operations": [
                {
                    "operation": "UPSERT",
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

    operation = result.semantic_operations[0]

    assert operation.operation == MemoryOperation.UPSERT
    assert operation.category.value == "constraint"
    assert operation.value["amount"] == 30000

    logger.info("test.memory_extractor_dict_validation_passed")


@pytest.mark.asyncio
async def test_memory_extractor_accepts_forget_operation():
    llm = MagicMock()
    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock(
        return_value={
            "semantic_operations": [
                {
                    "operation": "FORGET",
                    "category": "preference",
                    "key": "preferred_phone_brand",
                    "value": None,
                    "confidence": 1.0,
                }
            ],
            "episodic_memories": [],
        }
    )

    result = await extractor.extract(
        customer_message=(
            "Forget my preference for Samsung phones."
        )
    )

    assert len(result.semantic_operations) == 1

    operation = result.semantic_operations[0]

    assert operation.operation == MemoryOperation.FORGET
    assert operation.category.value == "preference"
    assert operation.key == "preferred_phone_brand"
    assert operation.value is None

    logger.info("test.memory_extractor_forget_passed")



@pytest.mark.asyncio
async def test_memory_extractor_receives_existing_memories():
    llm = MagicMock()
    extractor = MemoryExtractor(llm)

    extractor.chain = MagicMock()
    extractor.chain.ainvoke = AsyncMock(
        return_value={
            "semantic_operations": [
                {
                    "operation": "FORGET",
                    "category": "preference",
                    "key": "preferred_phone_brand",
                    "value": None,
                    "confidence": 1.0,
                }
            ],
            "episodic_memories": [],
        }
    )

    existing_memories = [
        {
            "category": "preference",
            "key": "preferred_phone_brand",
            "value": {"brand": "Samsung"},
        },
        {
            "category": "constraint",
            "key": "phone_budget",
            "value": {
                "amount": 30000,
                "currency": "INR",
            },
        },
    ]

    result = await extractor.extract(
        customer_message="Forget my preference for Samsung phones.",
        existing_memories=existing_memories,
    )

    print(result.model_dump_json(indent=2))

    assert len(result.semantic_operations) == 1
    assert result.semantic_operations[0].operation == (
        MemoryOperation.FORGET
    )

    call_args = extractor.chain.ainvoke.await_args.args[0]

    assert call_args["customer_message"] == (
        "Forget my preference for Samsung phones."
    )

    assert (
        "preferred_phone_brand"
        in call_args["existing_memories"]
    )

    logger.info(
        "test.memory_extractor_existing_context_passed"
    )
