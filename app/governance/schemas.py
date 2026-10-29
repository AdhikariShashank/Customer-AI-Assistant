
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GovernanceDecision(StrEnum):
    """Possible final or individual policy decisions."""

    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class PolicyContext(BaseModel):
    """Trusted information used to evaluate policies for one task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    operation: str
    user_id: int | None = None

    # Resolved by the executor and validated against the operation schema.
    arguments: dict[str, Any] = Field(default_factory=dict)

    # Additional trusted facts gathered for applicable policies.
    attributes: dict[str, Any] = Field(default_factory=dict)


class PolicyResult(BaseModel):
    """Outcome from one individual policy."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    decision: GovernanceDecision
    reason_code: str
    message: str | None = None


class GovernanceResult(BaseModel):
    """Combined governance decision for one planned task."""

    model_config = ConfigDict(extra="forbid")

    decision: GovernanceDecision

    # Stable machine-readable reasons explaining the final decision.
    reason_codes: list[str] = Field(default_factory=list)

    # Policies whose conditions matched the task's context.
    matched_policy_ids: list[str] = Field(default_factory=list)

    # Policies actually evaluated, including non-matching policies.
    evaluated_policy_ids: list[str] = Field(default_factory=list)

    # Individual policy outcomes, retained for diagnostics and tests.
    policy_results: list[PolicyResult] = Field(default_factory=list)
