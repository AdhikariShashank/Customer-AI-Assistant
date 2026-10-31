from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import app.planner.executor as executor_module

from app.planner.executor import SequentialExecutor
from app.planner.scheduler import DependencyAwareScheduler
from app.planner.operations import OperationSpec
from app.planner.schemas import Plan, Task

from app.governance.schemas import (
    GovernanceDecision,
    GovernanceResult,
    PolicyResult,
)


class EmptyArguments(BaseModel):
    pass


@pytest.mark.anyio
async def test_executor_pauses_for_approval_without_skipping_dependents(
    monkeypatch,
):
    # --------------------------------------------------
    # 1. Mock tools
    # --------------------------------------------------

    place_order_tool = MagicMock()
    place_order_tool.ainvoke = AsyncMock(
        return_value={"ok": True, "order_id": 501}
    )

    get_order_tool = MagicMock()
    get_order_tool.ainvoke = AsyncMock(
        return_value={"ok": True, "order_id": 501}
    )

    list_orders_tool = MagicMock()
    list_orders_tool.ainvoke = AsyncMock(
        return_value={"ok": True, "orders": []}
    )

    # --------------------------------------------------
    # 2. Build operation registry
    # --------------------------------------------------

    registry = {
        "place_order": OperationSpec(
            name="place_order",
            arguments_schema=EmptyArguments,
            execute=place_order_tool,
            access="write",
            output_description="Places an order.",
        ),
        "get_order": OperationSpec(
            name="get_order",
            arguments_schema=EmptyArguments,
            execute=get_order_tool,
            access="read",
            output_description="Retrieves an order.",
        ),
        "list_orders": OperationSpec(
            name="list_orders",
            arguments_schema=EmptyArguments,
            execute=list_orders_tool,
            access="read",
            output_description="Lists orders.",
        ),
    }

    # --------------------------------------------------
    # 3. Build plan
    # --------------------------------------------------

    plan = Plan(
        goal="Place an order and retrieve order information.",
        tasks=[
            Task(
                id="task_1",
                operation="place_order",
                description="Place the order.",
                arguments={},
            ),
            Task(
                id="task_2",
                operation="get_order",
                description="Retrieve the newly placed order.",
                arguments={},
                depends_on=["task_1"],
            ),
            Task(
                id="task_3",
                operation="list_orders",
                description="List existing orders.",
                arguments={},
            ),
        ],
    )

    # --------------------------------------------------
    # 4. Mock governance context builder
    # --------------------------------------------------

    checkout_facts = {
        "cart_id": 10,
        "order_total": "6500.00",
        "currency": "INR",
        "cart_snapshot": {
            "cart_id": 10,
            "items": [],
            "total": "6500.00",
        },
    }

    class FakeGovernanceContextBuilder:

        async def build(self, context):
            if context.operation == "place_order":
                return context.model_copy(
                    update={"attributes": checkout_facts}
                )

            return context

    # --------------------------------------------------
    # 5. Mock governance engine
    # --------------------------------------------------

    class FakeGovernanceEngine:

        def evaluate(self, context):
            if context.operation == "place_order":
                return GovernanceResult(
                    decision=GovernanceDecision.REQUIRE_APPROVAL,
                    reason_codes=["HIGH_VALUE_ORDER"],
                    matched_policy_ids=["high_value_order"],
                    evaluated_policy_ids=["high_value_order"],
                    policy_results=[
                        PolicyResult(
                            policy_id="high_value_order",
                            decision=GovernanceDecision.REQUIRE_APPROVAL,
                            reason_code="HIGH_VALUE_ORDER",
                            message="Admin approval required.",
                        )
                    ],
                )

            return GovernanceResult(
                decision=GovernanceDecision.ALLOW,
                reason_codes=[],
                matched_policy_ids=[],
                evaluated_policy_ids=[],
                policy_results=[],
            )

    # --------------------------------------------------
    # 6. Mock approval service
    # --------------------------------------------------

    approval_service = MagicMock()

    approval_service.create_request = AsyncMock(
        return_value=SimpleNamespace(
            id=101,
            status="PENDING",
        )
    )

    @asynccontextmanager
    async def approval_service_context():
        yield approval_service

    # --------------------------------------------------
    # 7. Capture scheduler state
    # --------------------------------------------------

    captured = {}

    class CapturingScheduler(DependencyAwareScheduler):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["scheduler"] = self

    monkeypatch.setattr(
        executor_module,
        "DependencyAwareScheduler",
        CapturingScheduler,
    )

    # --------------------------------------------------
    # 8. Create executor
    # --------------------------------------------------

    executor = SequentialExecutor(
        registry=registry,
        max_batch_size=5,
        governance_engine=FakeGovernanceEngine(),
        governance_context_builder=FakeGovernanceContextBuilder(),
        approval_service_context=approval_service_context,
    )

    # --------------------------------------------------
    # 9. Execute
    # --------------------------------------------------

    results = await executor.execute(
        plan=plan,
        user_id=7,
    )

    # --------------------------------------------------
    # 10. Verify checkout behavior
    # --------------------------------------------------

    # Checkout must never execute before approval.
    place_order_tool.ainvoke.assert_not_awaited()

    # Approval must be created exactly once.
    approval_service.create_request.assert_awaited_once()

    # Approval result must be returned.
    assert results["task_1"]["approval_required"] is True
    assert results["task_1"]["approval_id"] == 101
    assert (
        results["task_1"]["execution_status"]
        == "WAITING_FOR_APPROVAL"
    )

    # --------------------------------------------------
    # 11. Verify dependent task behavior
    # --------------------------------------------------

    # This task depends on successful checkout.
    get_order_tool.ainvoke.assert_not_awaited()

    # It must remain pending, not skipped.
    scheduler = captured["scheduler"]

    assert scheduler.statuses["task_1"] == "waiting_for_approval"
    assert scheduler.statuses["task_2"] == "pending"

    # --------------------------------------------------
    # 12. Verify independent task behavior
    # --------------------------------------------------

    # Independent work should still execute.
    list_orders_tool.ainvoke.assert_awaited_once()

    assert scheduler.statuses["task_3"] == "succeeded"

    # Dependent task should not be returned as skipped.
    assert "task_2" not in results