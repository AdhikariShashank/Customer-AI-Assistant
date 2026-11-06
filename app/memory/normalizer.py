
import re

from app.memory.schemas import (
    MemoryExtractionResult,
    MemoryOperation,
    SemanticMemoryOperation,
    EpisodicMemoryCandidate,
)


import logging

logger = logging.getLogger(__name__)


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

        logger.info(
            "memory.normalization_started operations=%d episodes=%d",
            len(result.semantic_operations),
            len(result.episodic_memories),
        )

        operations = []
        seen = set()

        for memory in result.semantic_operations:
            key = self.normalize_key(memory.key)
            category = memory.category.value

            value = (
                dict(memory.value)
                if memory.value is not None
                else None
            )

            if (
                memory.operation == MemoryOperation.UPSERT
                and key == "phone_budget"
                and value is not None
            ):
                if "max_budget" in value:
                    value["amount"] = value.pop("max_budget")

                original_key = self.normalize_identifier(
                    memory.key
                )

                if (
                    "currency" not in value
                    and original_key.endswith("_inr")
                ):
                    value["currency"] = "INR"

            identity = (
                memory.operation.value,
                category,
                key,
            )

            if identity in seen:
                logger.debug(
                    "memory.normalization_duplicate_skipped "
                    "category=%s",
                    category,
                )
                continue

            seen.add(identity)

            operations.append(
                SemanticMemoryOperation(
                    operation=memory.operation,
                    category=memory.category,
                    key=key,
                    value=value,
                    confidence=memory.confidence,
                )
            )

        episodes = [
            EpisodicMemoryCandidate(
                event_type=self.normalize_event_type(
                    episode.event_type
                ),
                description=episode.description.strip(),
                episode_metadata=episode.episode_metadata,
            )
            for episode in result.episodic_memories
        ]

        logger.info(
            "memory.normalization_completed "
            "operations=%d episodes=%d",
            len(operations),
            len(episodes),
        )

        return MemoryExtractionResult(
            semantic_operations=operations,
            episodic_memories=episodes,
        )
