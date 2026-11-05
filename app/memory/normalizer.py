
import re

from app.memory.schemas import (
    MemoryExtractionResult,
    SemanticMemoryCandidate,
    EpisodicMemoryCandidate,
)


class MemoryNormalizer:

    KEY_ALIASES = {
        "favorite_phone_brand": "preferred_phone_brand",
        "preferred_mobile_brand": "preferred_phone_brand",
        "phone_brand_preference": "preferred_phone_brand",

        "phone_budget_inr": "phone_budget",
        "mobile_budget": "phone_budget",
        "mobile_phone_budget": "phone_budget",
    }

    EVENT_ALIASES = {
        "delivery_problem": "delivery_issue",
        "late_delivery": "delivery_issue",
        "delayed_order": "delivery_issue",

        "refund_requested": "refund_request",
        "requested_refund": "refund_request",
    }

    @staticmethod
    def normalize_identifier(value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "_", value)
        return value.strip("_")

    def normalize_key(self, key: str) -> str:
        normalized = self.normalize_identifier(key)
        return self.KEY_ALIASES.get(normalized, normalized)

    def normalize_event_type(self, event_type: str) -> str:
        normalized = self.normalize_identifier(event_type)
        return self.EVENT_ALIASES.get(normalized, normalized)

    def normalize(
        self,
        result: MemoryExtractionResult,
    ) -> MemoryExtractionResult:

        semantic_memories = []
        seen_semantic = set()

        for memory in result.semantic_memories:
            key = self.normalize_key(memory.key)
            category = memory.category.value

            value = dict(memory.value)

            # Normalize the known phone-budget representation.
            if key == "phone_budget":
                if "max_budget" in value:
                    value["amount"] = value.pop("max_budget")

                if "currency" not in value:
                    original_key = self.normalize_identifier(
                        memory.key
                    )

                    if original_key.endswith("_inr"):
                        value["currency"] = "INR"

            identity = (category, key)

            if identity in seen_semantic:
                continue

            seen_semantic.add(identity)

            semantic_memories.append(
                SemanticMemoryCandidate(
                    category=memory.category,
                    key=key,
                    value=value,
                    confidence=memory.confidence,
                )
            )

        episodic_memories = []

        for episode in result.episodic_memories:
            episodic_memories.append(
                EpisodicMemoryCandidate(
                    event_type=self.normalize_event_type(
                        episode.event_type
                    ),
                    description=episode.description.strip(),
                    episode_metadata=episode.episode_metadata,
                )
            )

        return MemoryExtractionResult(
            semantic_memories=semantic_memories,
            episodic_memories=episodic_memories,
        )
