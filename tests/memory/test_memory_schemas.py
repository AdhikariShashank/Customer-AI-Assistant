import pytest
from pydantic import ValidationError

from app.memory.schemas import (
    MemoryExtractionResult,
    SemanticMemoryCandidate,
)


def test_valid_semantic_memory():
    memory = SemanticMemoryCandidate(
        category="preference",
        key="preferred_phone_brand",
        value={"brand": "Samsung"},
        confidence=0.95,
    )

    assert memory.category == "preference"
    assert memory.value["brand"] == "Samsung"


def test_invalid_category():
    with pytest.raises(ValidationError):
        SemanticMemoryCandidate(
            category="random_category",
            key="phone_brand",
            value={"brand": "Samsung"},
            confidence=0.95,
        )


def test_invalid_confidence():
    with pytest.raises(ValidationError):
        SemanticMemoryCandidate(
            category="preference",
            key="phone_brand",
            value={"brand": "Samsung"},
            confidence=1.5,
        )


def test_empty_extraction_result():
    result = MemoryExtractionResult()

    assert result.semantic_memories == []
    assert result.episodic_memories == []