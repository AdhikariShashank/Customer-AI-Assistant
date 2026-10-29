
import pytest
from pydantic import ValidationError

from app.governance.schemas import (
    GovernanceDecision,
    GovernanceResult,
    PolicyContext,
    PolicyResult,
)


def test_policy_context_accepts_valid_task():
    context = PolicyContext(
        task_id="T1",
        operation="place_order",
        user_id=42,
        arguments={"cart_id": 105},
        attributes={
            "order_total": 80000,
            "currency": "INR",
        },
    )

    assert context.operation == "place_order"
    assert context.arguments["cart_id"] == 105
    assert context.attributes["order_total"] == 80000


def test_policy_context_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        PolicyContext(
            task_id="T1",
            operation="place_order",
            unexpected_field="value",
        )


def test_policy_result_accepts_approval_decision():
    result = PolicyResult(
        policy_id="high_value_order",
        decision=GovernanceDecision.REQUIRE_APPROVAL,
        reason_code="HIGH_VALUE_ORDER",
    )

    assert result.decision == GovernanceDecision.REQUIRE_APPROVAL


def test_governance_result_preserves_policy_outcomes():
    policy_result = PolicyResult(
        policy_id="high_value_order",
        decision=GovernanceDecision.REQUIRE_APPROVAL,
        reason_code="HIGH_VALUE_ORDER",
    )

    result = GovernanceResult(
        decision=GovernanceDecision.REQUIRE_APPROVAL,
        reason_codes=["HIGH_VALUE_ORDER"],
        matched_policy_ids=["high_value_order"],
        evaluated_policy_ids=["high_value_order"],
        policy_results=[policy_result],
    )

    assert result.decision == GovernanceDecision.REQUIRE_APPROVAL
    assert result.matched_policy_ids == ["high_value_order"]
    assert result.evaluated_policy_ids == ["high_value_order"]
    assert len(result.policy_results) == 1
