
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.execution_resolution import ExecutionResolutionService
from app.planner.exceptions import TaskExecutionError
from pydantic import BaseModel

from app.planner.operations import OperationSpec
from app.planner.schemas import Plan


@pytest.fixture
def execution_repository():
    return AsyncMock()


@pytest.fixture
def service(execution_repository):
    return ExecutionResolutionService(
        execution_repository=execution_repository,
        operation_registry={},
    )


@pytest.fixture
def execution():
    obj = MagicMock()
    obj.id = 101
    obj.status = "RUNNING"
    obj.waiting_task_id = "task_2"
    obj.plan = {}
    obj.task_statuses = {}
    obj.results = {}
    return obj


@pytest.mark.asyncio
async def test_reject_resolution_when_execution_not_waiting(
    service,
    execution,
    execution_repository,
):
    with pytest.raises(TaskExecutionError):
        await service.resolve_approval(
            execution=execution,
            task_id="task_2",
            outcome="expired",
            approval_id=55,
        )

    execution_repository.update_state.assert_not_called()


@pytest.mark.asyncio
async def test_reject_resolution_when_task_id_does_not_match(
    service,
    execution,
    execution_repository,
):
    execution.status = "WAITING_FOR_APPROVAL"

    with pytest.raises(TaskExecutionError):
        await service.resolve_approval(
            execution=execution,
            task_id="task_3",
            outcome="expired",
            approval_id=55,
        )

    execution_repository.update_state.assert_not_called()


@pytest.mark.asyncio
async def test_reject_unsupported_outcome(
    service,
    execution,
    execution_repository,
):
    execution.status = "WAITING_FOR_APPROVAL"

    with pytest.raises(ValueError):
        await service.resolve_approval(
            execution=execution,
            task_id="task_2",
            outcome="approved",
            approval_id=55,
        )

    execution_repository.update_state.assert_not_called()



class EmptyArguments(BaseModel):
    pass


def build_test_registry():
    """Create a minimal registry for the operations in our test plan."""

    operations = {
        "search_products": "read",
        "place_order": "write",
        "get_order": "read",
        "list_orders": "read",
        "get_product": "read",
    }

    return {
        name: OperationSpec(
            name=name,
            arguments_schema=EmptyArguments,
            execute=MagicMock(),
            access=access,
            output_description=f"Test output for {name}",
        )
        for name, access in operations.items()
    }


@pytest.fixture
def waiting_execution():
    plan = Plan(
        goal="Place an order and retrieve its details.",
        tasks=[
            {
                "id": "task_1",
                "operation": "search_products",
                "description": "Search products",
            },
            {
                "id": "task_2",
                "operation": "place_order",
                "description": "Place order",
            },
            {
                "id": "task_3",
                "operation": "get_order",
                "description": "Retrieve placed order",
                "depends_on": ["task_2"],
            },
            {
                "id": "task_4",
                "operation": "list_orders",
                "description": "List existing orders",
            },
            {
                "id": "task_5",
                "operation": "get_product",
                "description": "Retrieve product details",
                "depends_on": ["task_3"],
            },
        ],
    )

    execution = MagicMock()
    execution.id = 101
    execution.status = "WAITING_FOR_APPROVAL"
    execution.waiting_task_id = "task_2"
    execution.plan = plan.model_dump(mode="json")

    execution.task_statuses = {
        "task_1": "succeeded",
        "task_2": "waiting_for_approval",
        "task_3": "pending",
        "task_4": "pending",
        "task_5": "pending",
    }

    execution.results = {
        "task_1": {
            "success": True,
            "data": {"product_id": 42},
        }
    }

    return execution


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected_error_code"),
    [
        ("expired", "APPROVAL_EXPIRED"),
        ("rejected", "APPROVAL_REJECTED"),
    ],
)
async def test_successful_approval_resolution(
    outcome,
    expected_error_code,
    execution_repository,
    waiting_execution,
):
    async def update_execution(
        execution,
        *,
        results,
        task_statuses,
        status,
        waiting_task_id,
    ):
        execution.results = results
        execution.task_statuses = task_statuses
        execution.status = status
        execution.waiting_task_id = waiting_task_id
        return execution

    execution_repository.update_state.side_effect = update_execution

    service = ExecutionResolutionService(
        execution_repository=execution_repository,
        operation_registry=build_test_registry(),
    )

    result = await service.resolve_approval(
        execution=waiting_execution,
        task_id="task_2",
        outcome=outcome,
        approval_id=55,
    )

    # Execution-level state.
    assert result.status == "FAILED"
    assert result.waiting_task_id is None

    # Scheduler task statuses.
    assert result.task_statuses == {
        "task_1": "succeeded",
        "task_2": outcome,
        "task_3": "skipped",
        "task_4": "pending",
        "task_5": "skipped",
    }

    # Waiting task result.
    assert result.results["task_2"]["success"] is False
    assert result.results["task_2"]["error"]["code"] == expected_error_code
    assert result.results["task_2"]["approval"] == {
        "approval_id": 55,
        "status": outcome,
    }

    # Dependent task results.
    assert result.results["task_3"]["status"] == "skipped"
    assert result.results["task_5"]["status"] == "skipped"

    # Independent task remains untouched.
    assert "task_4" not in result.results

    # Existing successful result must be preserved.
    assert result.results["task_1"] == {
        "success": True,
        "data": {"product_id": 42},
    }

    execution_repository.update_state.assert_awaited_once()
