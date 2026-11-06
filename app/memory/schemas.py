
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryCategory(StrEnum):
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    INTEREST = "interest"
    PROFILE = "profile"
    GOAL = "goal"


class MemoryOperation(StrEnum):
    UPSERT = "UPSERT"
    FORGET = "FORGET"


class SemanticMemoryOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: MemoryOperation
    category: MemoryCategory
    key: str = Field(min_length=1, max_length=150)
    value: dict[str, Any] | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_operation(self):
        if self.operation == MemoryOperation.UPSERT:
            if not self.value:
                raise ValueError(
                    "UPSERT requires a non-empty value"
                )

        if self.operation == MemoryOperation.FORGET:
            if self.value is not None:
                raise ValueError(
                    "FORGET must not contain a value"
                )

        return self


class EpisodicMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    episode_metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class MemoryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_operations: list[SemanticMemoryOperation] = Field(
        default_factory=list
    )
    episodic_memories: list[EpisodicMemoryCandidate] = Field(
        default_factory=list
    )
