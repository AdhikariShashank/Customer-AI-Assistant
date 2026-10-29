from app.governance.policies.order_policies import (
    high_value_order_policy,
)
from app.governance.schemas import (
    GovernanceDecision,
    PolicyContext,
)


def make_context(
    *,
    operation: str = "place_order",
    order_total=None,
    currency="INR",
) -> PolicyContext:
    attributes = {"currency": currency}

    if order_total is not None:
        attributes["order_total"] = order_total

    return PolicyContext(
        task_id="T1",
        operation=operation,
        user_id=42,
        attributes=attributes,
    )


def test_order_above_threshold_requires_approval():
    result = high_value_order_policy(
        make_context(order_total="5000.01")
    )

    assert result is not None
    assert result.decision == GovernanceDecision.REQUIRE_APPROVAL
    assert result.reason_code == "HIGH_VALUE_ORDER"


def test_order_exactly_at_threshold_is_not_restricted():
    result = high_value_order_policy(
        make_context(order_total="5000.00")
    )

    assert result is None


def test_order_below_threshold_is_not_restricted():
    result = high_value_order_policy(
        make_context(order_total="4999.99")
    )

    assert result is None


def test_missing_order_total_denies():
    result = high_value_order_policy(make_context())

    assert result is not None
    assert result.decision == GovernanceDecision.DENY
    assert result.reason_code == "ORDER_FACTS_MISSING"


def test_unsupported_currency_denies():
    result = high_value_order_policy(
        make_context(order_total="6000", currency="USD")
    )

    assert result is not None
    assert result.decision == GovernanceDecision.DENY
    assert result.reason_code == "UNSUPPORTED_POLICY_CURRENCY"


def test_policy_does_not_apply_to_product_search():
    result = high_value_order_policy(
        make_context(
            operation="search_products",
            order_total=None,
        )
    )

    assert result is None