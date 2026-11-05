from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryCategory(StrEnum):
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    INTEREST = "interest"
    PROFILE = "profile"
    GOAL = "goal"


class SemanticMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory
    key: str = Field(min_length=1, max_length=150)
    value: dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)


class EpisodicMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    episode_metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_memories: list[SemanticMemoryCandidate] = Field(
        default_factory=list
    )

    episodic_memories: list[EpisodicMemoryCandidate] = Field(
        default_factory=list
    )