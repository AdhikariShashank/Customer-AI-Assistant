
from app.governance.engine import GovernanceEngine
from app.governance.policy import identified_policy
from app.governance.registry import PolicyRegistry
from app.governance.schemas import (
    GovernanceDecision,
    PolicyContext,
    PolicyResult,
)
from app.governance.setup import build_governance_engine


def make_context(
    operation: str = "place_order",
    total: str = "6000",
) -> PolicyContext:
    return PolicyContext(
        task_id="T1",
        operation=operation,
        attributes={
            "order_total": total,
            "currency": "INR",
        },
    )


@identified_policy("approval_policy")
def approval_policy(ctx: PolicyContext) -> PolicyResult:
    return PolicyResult(
        policy_id="approval_policy",
        decision=GovernanceDecision.REQUIRE_APPROVAL,
        reason_code="HIGH_VALUE_ORDER",
    )


@identified_policy("deny_policy")
def deny_policy(ctx: PolicyContext) -> PolicyResult:
    return PolicyResult(
        policy_id="deny_policy",
        decision=GovernanceDecision.DENY,
        reason_code="ORDER_BLOCKED",
    )


@identified_policy("non_matching_policy")
def non_matching_policy(ctx: PolicyContext) -> None:
    return None


def test_high_value_order_requires_approval():
    result = build_governance_engine().evaluate(make_context())

    assert result.decision == GovernanceDecision.REQUIRE_APPROVAL
    assert "high_value_order" in result.matched_policy_ids
    assert "high_value_order" in result.evaluated_policy_ids


def test_deny_takes_precedence_over_approval():
    registry = PolicyRegistry()
    registry.register("place_order", approval_policy)
    registry.register("place_order", deny_policy)

    result = GovernanceEngine(registry).evaluate(make_context())

    assert result.decision == GovernanceDecision.DENY


def test_non_matching_policy_is_evaluated_but_not_matched():
    registry = PolicyRegistry()
    registry.register("place_order", non_matching_policy)

    result = GovernanceEngine(registry).evaluate(make_context())

    assert result.decision == GovernanceDecision.ALLOW
    assert result.evaluated_policy_ids == ["non_matching_policy"]
    assert result.matched_policy_ids == []


def test_required_policy_missing_fails_closed():
    registry = PolicyRegistry()
    registry.register("place_order", approval_policy)
    registry.register("place_order", deny_policy)

    # Simulate accidental removal of a required policy.
    registry._policies["place_order"] = [deny_policy]

    result = GovernanceEngine(registry).evaluate(make_context())

    assert result.decision == GovernanceDecision.DENY
    assert result.reason_codes == [
        "GOVERNANCE_REQUIRED_POLICY_MISSING"
    ]


def test_unregistered_operation_does_not_block_other_features():
    registry = PolicyRegistry()

    result = GovernanceEngine(registry).evaluate(
        make_context(operation="search_products")
    )

    assert result.decision == GovernanceDecision.ALLOW
