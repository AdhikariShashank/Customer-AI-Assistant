
from app.governance.engine import GovernanceEngine
from app.governance.policies.order_policies import (
    high_value_order_policy,
)
from app.governance.registry import PolicyRegistry


def build_governance_engine() -> GovernanceEngine:
    registry = PolicyRegistry()

    registry.register(
        operation="place_order",
        policy=high_value_order_policy,
        required=True,
    )

    return GovernanceEngine(registry)
