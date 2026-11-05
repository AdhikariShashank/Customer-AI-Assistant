from dataclasses import dataclass, field

from app.models.user_memory import UserMemory
from app.models.user_episode import UserEpisode
from app.services.semantic_memory import SemanticMemoryService
from app.services.episodic_memory import EpisodicMemoryService


@dataclass
class RetrievedMemories:
    semantic: list[UserMemory] = field(default_factory=list)
    episodic: list[UserEpisode] = field(default_factory=list)


class MemoryRetriever:

    def __init__(
        self,
        semantic_service: SemanticMemoryService,
        episodic_service: EpisodicMemoryService,
    ):
        self.semantic_service = semantic_service
        self.episodic_service = episodic_service

    async def retrieve(
        self,
        *,
        user_id: int,
        semantic_limit: int = 30,
        episodic_limit: int = 10,
        categories: set[str] | None = None,
        event_types: set[str] | None = None,
    ) -> RetrievedMemories:

        if user_id <= 0:
            raise ValueError("user_id must be positive")

        if not 1 <= semantic_limit <= 100:
            raise ValueError("semantic_limit must be between 1 and 100")

        if not 1 <= episodic_limit <= 100:
            raise ValueError("episodic_limit must be between 1 and 100")

        # Retrieve active semantic memories.
        semantic = await self.semantic_service.get_active_memories(
            user_id=user_id,
            limit=semantic_limit,
        )

        # Optional category filtering.
        if categories is not None:
            semantic = [
                memory
                for memory in semantic
                if memory.category in categories
            ]

        # Retrieve recent episodic memories.
        episodic = await self.episodic_service.get_recent_events(
            user_id=user_id,
            limit=episodic_limit,
        )

        # Optional event type filtering.
        if event_types is not None:
            episodic = [
                episode
                for episode in episodic
                if episode.event_type in event_types
            ]

        return RetrievedMemories(
            semantic=semantic,
            episodic=episodic,
        )