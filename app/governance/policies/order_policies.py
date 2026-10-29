from decimal import Decimal, InvalidOperation
from typing import Any

from app.governance.policy import Policy
from app.governance.schemas import (
    GovernanceDecision,
    PolicyContext,
    PolicyResult,
)
from app.governance.policy import Policy, identified_policy

HIGH_VALUE_ORDER_POLICY_ID = "high_value_order"
HIGH_VALUE_ORDER_REASON = "HIGH_VALUE_ORDER"
ORDER_FACTS_MISSING_REASON = "ORDER_FACTS_MISSING"

DEFAULT_HIGH_VALUE_THRESHOLD = Decimal("5000.00")


def _parse_order_total(value: Any) -> Decimal | None:
    """Convert a supported numeric value to Decimal safely."""

    if isinstance(value, bool):
        return None

    try:
        total = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not total.is_finite() or total < 0:
        return None

    return total


@identified_policy("high_value_order")
def high_value_order_policy(
    context: PolicyContext,
) -> PolicyResult | None:
    """Require approval for INR orders strictly above the threshold."""

    # This rule applies only to order placement.
    if context.operation != "place_order":
        return None

    total_value = context.attributes.get("order_total")
    currency = context.attributes.get("currency")

    # Missing or invalid facts must not accidentally allow checkout.
    total = _parse_order_total(total_value)

    if total is None or not isinstance(currency, str) or not currency.strip():
        return PolicyResult(
            policy_id=HIGH_VALUE_ORDER_POLICY_ID,
            decision=GovernanceDecision.DENY,
            reason_code=ORDER_FACTS_MISSING_REASON,
            message="Required order facts are missing or invalid.",
        )

    if currency.upper() != "INR":
        return PolicyResult(
            policy_id=HIGH_VALUE_ORDER_POLICY_ID,
            decision=GovernanceDecision.DENY,
            reason_code="UNSUPPORTED_POLICY_CURRENCY",
            message="The high-value order policy cannot evaluate this currency.",
        )

    if total > DEFAULT_HIGH_VALUE_THRESHOLD:
        return PolicyResult(
            policy_id=HIGH_VALUE_ORDER_POLICY_ID,
            decision=GovernanceDecision.REQUIRE_APPROVAL,
            reason_code=HIGH_VALUE_ORDER_REASON,
            message="Orders above ₹5,000 require approval.",
        )

    # The rule was evaluated and does not restrict this order.
    return None


HIGH_VALUE_ORDER_POLICY: Policy = high_value_order_policy