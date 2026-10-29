
import pytest

from app.governance.context_builder import GovernanceContextBuilder
from app.governance.schemas import GovernanceDecision, PolicyContext
from app.governance.setup import build_governance_engine
from app.services.order import OrderService
from app.tools.dependencies import order_service_context


@pytest.mark.anyio
async def test_missing_checkout_facts_returns_deny(monkeypatch):
    # Arrange: simulate checkout facts being unavailable.
    async def mock_get_checkout_facts(self, user_id: int):
        return None

    monkeypatch.setattr(
        OrderService,
        "get_checkout_facts",
        mock_get_checkout_facts,
    )

    builder = GovernanceContextBuilder(
        order_service_context=order_service_context,
    )
    engine = build_governance_engine()

    context = PolicyContext(
        task_id="test-place-order",
        operation="place_order",
        user_id=2,  # Use a valid test user ID for your app.
    )

    # Act: build the context and evaluate governance.
    enriched_context = await builder.build(context)
    result = engine.evaluate(enriched_context)

    # Assert: missing facts must fail closed.
    assert "order_total" not in enriched_context.attributes
    assert "currency" not in enriched_context.attributes
    assert result.decision == GovernanceDecision.DENY
    assert "ORDER_FACTS_MISSING" in result.reason_codes
