
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel
import pytest

from app.planner.schemas import Task

from app.models.agent_execution import ExecutionStatus
from app.planner.exceptions import TaskExecutionError
from app.planner.executor import SequentialExecutor
from app.planner.schemas import Plan


@pytest.fixture
def plan_data():
    return {
        "tasks": [
            {
                "id": "task_1",
                "operation": "get_active_cart",
                "arguments": {},
                "depends_on": [],
                "input_refs": {},
            },
            {
                "id": "task_2",
                "operation": "place_order",
                "arguments": {},
                "depends_on": ["task_1"],
                "input_refs": {},
            },
        ]
    }


@pytest.fixture
def persisted_execution():
    return SimpleNamespace(
        id=10,
        user_id=5,
        status=ExecutionStatus.WAITING_FOR_APPROVAL.value,
        waiting_task_id="task_2",
        plan={
            "goal": "Add products to cart and place an order",
            "tasks": [
                {
                    "id": "task_1",
                    "operation": "get_active_cart",
                    "description": "Retrieve the user's active cart",
                    "arguments": {},
                    "depends_on": [],
                    "input_refs": {},
                },
                {
                    "id": "task_2",
                    "operation": "place_order",
                    "description": "Place the order after approval",
                    "arguments": {},
                    "depends_on": ["task_1"],
                    "input_refs": {},
                },
            ],
        },
        results={
            "task_1": {
                "cart_id": 20,
                "total": "7500.00",
            }
        },
        task_statuses={
            "task_1": "succeeded",
            "task_2": "waiting_for_approval",
        },
    )


@pytest.fixture
def approved_request():
    return SimpleNamespace(
        id=30,
        user_id=5,
        execution_id=10,
        waiting_task_id="task_2",
        status="APPROVED",
        cart_snapshot={
            "cart_id": 20,
            "items": [
                {
                    "product_id": 1,
                    "quantity": 2,
                }
            ],
        },
    )


@pytest.fixture
def approval_service(approved_request):
    service = MagicMock()
    service.get_approved_request = AsyncMock(
        return_value=approved_request
    )
    return service


@pytest.fixture
def execution_service(persisted_execution):
    service = MagicMock()

    service.get_execution_for_user = AsyncMock(
        return_value=persisted_execution
    )

    service.claim_for_resume = AsyncMock(
        return_value=SimpleNamespace(
            id=10,
            status=ExecutionStatus.RESUMING.value,
        )
    )

    return service


@pytest.fixture
def approval_context(approval_service):
    @asynccontextmanager
    async def factory():
        yield approval_service

    return factory


@pytest.fixture
def execution_context(execution_service):
    @asynccontextmanager
    async def factory():
        yield execution_service

    return factory


@pytest.fixture
def executor(approval_context, execution_context):
    registry = {
        "get_active_cart": SimpleNamespace(access="read"),
        "place_order": SimpleNamespace(access="write"),
    }

    return SequentialExecutor(
        registry=registry,
        approval_service_context=approval_context,
        execution_service_context=execution_context,
    )



@pytest.mark.asyncio
async def test_resume_success(
    executor,
    approval_service,
    execution_service,
    persisted_execution,
    approved_request,
):
    expected_result = {
        "execution_id": 10,
        "execution_status": "COMPLETED",
        "waiting_task_id": None,
        "results": {},
    }

    executor._run_execution_loop = AsyncMock(
        return_value=expected_result
    )

    result = await executor.resume(
        execution_id=10,
        user_id=5,
        approval_id=30,
        waiting_task_id="task_2",
    )

    assert result == expected_result

    approval_service.get_approved_request.assert_awaited_once_with(
        approval_id=30,
        user_id=5,
        execution_id=10,
        waiting_task_id="task_2",
    )

    execution_service.get_execution_for_user.assert_awaited_once_with(
        execution_id=10,
        user_id=5,
    )

    execution_service.claim_for_resume.assert_awaited_once_with(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_2",
    )

    executor._run_execution_loop.assert_awaited_once()

    loop_kwargs = (
        executor._run_execution_loop.await_args.kwargs
    )

    assert loop_kwargs["user_id"] == 5
    assert loop_kwargs["execution_id"] == 10
    assert loop_kwargs["approved_task_id"] == "task_2"
    assert loop_kwargs["approval_id"] == approved_request.id
    assert (
        loop_kwargs["expected_cart_snapshot"]
        == approved_request.cart_snapshot
    )

    assert (
        loop_kwargs["scheduler"].statuses["task_2"]
        == "pending"
    )



@pytest.mark.asyncio
async def test_resume_rejects_invalid_approval(
    executor,
    approval_service,
    execution_service,
):
    approval_service.get_approved_request = AsyncMock(
        return_value=None
    )

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.get_execution_for_user.assert_not_awaited()
    execution_service.claim_for_resume.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_rejects_missing_execution(
    executor,
    execution_service,
):
    execution_service.get_execution_for_user = AsyncMock(
        return_value=None
    )

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.claim_for_resume.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_rejects_execution_not_waiting_for_approval(
    executor,
    execution_service,
    persisted_execution,
):
    persisted_execution.status = ExecutionStatus.COMPLETED.value

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.claim_for_resume.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_rejects_mismatched_waiting_task(
    executor,
    execution_service,
    persisted_execution,
):
    persisted_execution.waiting_task_id = "task_1"

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.claim_for_resume.assert_not_awaited()

@pytest.mark.asyncio
async def test_resume_rejects_invalid_persisted_plan(
    executor,
    persisted_execution,
    execution_service,
):
    persisted_execution.plan = {
        "goal": "Place an order",
        "tasks": [],
    }

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.claim_for_resume.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_rejects_invalid_task_statuses(
    executor,
    persisted_execution,
    execution_service,
):
    persisted_execution.task_statuses = {
        "task_1": "succeeded",
        "task_2": "unknown_status",
    }

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.claim_for_resume.assert_not_awaited()

@pytest.mark.asyncio
async def test_resume_rejects_missing_waiting_task(
    executor,
    persisted_execution,
    execution_service,
):
    persisted_execution.plan["tasks"] = [
        task
        for task in persisted_execution.plan["tasks"]
        if task["id"] != "task_2"
    ]

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    execution_service.claim_for_resume.assert_not_awaited()

@pytest.mark.asyncio
async def test_resume_rejects_execution_already_claimed(
    executor,
    execution_service,
):
    execution_service.claim_for_resume = AsyncMock(
        side_effect=ValueError(
            "Execution cannot be claimed for resumption."
        )
    )

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    executor._run_execution_loop = AsyncMock()

    with pytest.raises(TaskExecutionError):
        await executor.resume(
            execution_id=10,
            user_id=5,
            approval_id=30,
            waiting_task_id="task_2",
        )

    executor._run_execution_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_runs_execution_loop_after_claim(
    executor,
    execution_service,
):
    call_order = []

    async def claim(**kwargs):
        call_order.append("claim")
        return SimpleNamespace(
            id=10,
            status=ExecutionStatus.RESUMING.value,
        )

    async def run_loop(**kwargs):
        call_order.append("run_loop")
        return {"execution_id": 10}

    execution_service.claim_for_resume = AsyncMock(
        side_effect=claim
    )

    executor._run_execution_loop = AsyncMock(
        side_effect=run_loop
    )

    await executor.resume(
        execution_id=10,
        user_id=5,
        approval_id=30,
        waiting_task_id="task_2",
    )

    assert call_order == ["claim", "run_loop"]

@pytest.mark.asyncio
async def test_execute_one_approved_checkout_bypasses_governance(
    executor,
):
    class EmptyArguments(BaseModel):
        pass

    expected_snapshot = {
        "cart_id": 20,
        "items": [
            {"product_id": 1, "quantity": 2}
        ],
    }

    execute = MagicMock()
    execute.ainvoke = AsyncMock(
        return_value={
            "ok": True,
            "order_id": 100,
        }
    )

    spec = SimpleNamespace(
        arguments_schema=EmptyArguments,
        execute=execute,
    )

    executor.registry["place_order"] = spec

    executor._check_governance = AsyncMock()

    task = Task(
        id="task_2",
        operation="place_order",
        description="Place the approved order",
        arguments={},
        depends_on=["task_1"],
        input_refs={},
    )

    task_id, result, failed = await executor._execute_one(
        task=task,
        completed_results={
            "task_1": {
                "cart_id": 20,
                "total": "7500.00",
            }
        },
        user_id=5,
        execution_id=10,
        approved_task_id="task_2",
        approval_id=30,
        expected_cart_snapshot=expected_snapshot,
    )

    assert task_id == "task_2"
    assert result == {
        "ok": True,
        "order_id": 100,
    }
    assert failed is False

    executor._check_governance.assert_not_awaited()

    execute.ainvoke.assert_awaited_once()

    call_args = execute.ainvoke.await_args

    assert call_args.args[0] == {}

    configurable = call_args.kwargs["config"]["configurable"]

    assert configurable["user_id"] == 5
    assert configurable["approval_id"] == 30
    assert configurable["expected_cart_snapshot"] == expected_snapshot


@pytest.mark.asyncio
async def test_execute_one_unapproved_checkout_runs_governance(executor):
    class EmptyArguments(BaseModel):
        pass

    execute = MagicMock()
    execute.ainvoke = AsyncMock(
        return_value={
            "ok": True,
            "order_id": 100,
        }
    )

    executor.registry["place_order"] = SimpleNamespace(
        arguments_schema=EmptyArguments,
        execute=execute,
    )

    governance_result = {
        "decision": "REQUIRE_APPROVAL",
        "reason": "High-value order requires approval",
        "approval_id": 30,
        "execution_status": "WAITING_FOR_APPROVAL",
    }

    executor._check_governance = AsyncMock(
        return_value=governance_result
    )

    task = Task(
        id="task_2",
        operation="place_order",
        description="Place an order",
        arguments={},
        depends_on=["task_1"],
        input_refs={},
    )

    task_id, result, failed = await executor._execute_one(
        task=task,
        completed_results={
            "task_1": {
                "cart_id": 20,
                "total": "7500.00",
            }
        },
        user_id=5,
        execution_id=10,
    )

    assert task_id == "task_2"
    assert result == governance_result
    assert failed is False

    executor._check_governance.assert_awaited_once()
    execute.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_completes_approved_checkout_end_to_end(
    executor,
    approval_service,
    execution_service,
):
    class EmptyArguments(BaseModel):
        pass

    expected_snapshot = {
        "cart_id": 20,
        "items": [
            {"product_id": 1, "quantity": 2}
        ],
    }

    # Mock only the actual checkout operation.
    execute = MagicMock()
    execute.ainvoke = AsyncMock(
        return_value={
            "ok": True,
            "order_id": 100,
            "message": "Order placed successfully",
        }
    )

    executor.registry["place_order"] = SimpleNamespace(
        access="write",
        arguments_schema=EmptyArguments,
        execute=execute,
    )

    # Governance must be bypassed for this exact approved task.
    executor._check_governance = AsyncMock()

    # Keep persistence outside this unit test.
    executor._persist_execution_state = AsyncMock()

    result = await executor.resume(
        execution_id=10,
        user_id=5,
        approval_id=30,
        waiting_task_id="task_2",
    )

    print("\nRESUME RESULT:", result)
    print("RESULT KEYS:", result.keys())

    # 1. Approval was validated.
    approval_service.get_approved_request.assert_awaited_once()

    # 2. Persisted execution was loaded and claimed.
    execution_service.get_execution_for_user.assert_awaited_once()
    execution_service.claim_for_resume.assert_awaited_once()

    # 3. The actual checkout operation executed.
    execute.ainvoke.assert_awaited_once()

    call_config = execute.ainvoke.await_args.kwargs["config"]["configurable"]

    assert call_config["user_id"] == 5
    assert call_config["approval_id"] == 30
    assert call_config["expected_cart_snapshot"] == expected_snapshot

    # 4. Governance was bypassed only for this approved task.
    executor._check_governance.assert_not_awaited()

    # 5. Execution completed successfully.
    assert result["execution_id"] == 10
    assert result["execution_status"] == "COMPLETED"
    assert result["waiting_task_id"] is None

    assert result["results"]["task_1"] == {
        "cart_id": 20,
        "total": "7500.00",
    }

    assert result["results"]["task_2"] == {
        "ok": True,
        "order_id": 100,
        "message": "Order placed successfully",
    }

    # The loop persists state before execution, after execution,
    # and when finalizing the execution.
    assert executor._persist_execution_state.await_count >= 2