
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_execution import ExecutionStatus
from app.repositories.agent_execution import AgentExecutionRepository


@pytest.fixture
def db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(db):
    return AgentExecutionRepository(db)


@pytest.fixture
def waiting_execution():
    return SimpleNamespace(
        id=10,
        user_id=5,
        status=ExecutionStatus.WAITING_FOR_APPROVAL.value,
        waiting_task_id="task_3",
        plan={
            "tasks": [
                {"id": "task_1", "operation": "get_active_cart"},
                {"id": "task_3", "operation": "place_order"},
            ]
        },
        task_statuses={
            "task_1": "succeeded",
            "task_3": "waiting_for_approval",
        },
    )

@pytest.mark.asyncio
async def test_claim_for_resume_success(
    repository,
    db,
    waiting_execution,
):
    repository.get_by_id_for_update = AsyncMock(
        return_value=waiting_execution
    )

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )

    assert result is waiting_execution
    assert result.status == ExecutionStatus.RESUMING.value

    repository.get_by_id_for_update.assert_awaited_once_with(
        execution_id=10,
        user_id=5,
    )

    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_for_resume_execution_not_found(repository, db):
    repository.get_by_id_for_update = AsyncMock(return_value=None)

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )

    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_for_resume_wrong_status(
    repository,
    db,
    waiting_execution,
):
    waiting_execution.status = ExecutionStatus.RESUMING.value

    repository.get_by_id_for_update = AsyncMock(
        return_value=waiting_execution
    )

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )

    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_for_resume_wrong_waiting_task(
    repository,
    db,
    waiting_execution,
):
    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_99",
    ) if False else None

    repository.get_by_id_for_update = AsyncMock(
        return_value=waiting_execution
    )

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_99",
    )

    assert result is None
    assert (
        waiting_execution.status
        == ExecutionStatus.WAITING_FOR_APPROVAL.value
    )
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_for_resume_invalid_plan(
    repository,
    db,
    waiting_execution,
):
    waiting_execution.plan = None

    repository.get_by_id_for_update = AsyncMock(
        return_value=waiting_execution
    )

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )

    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_for_resume_task_not_in_plan(
    repository,
    db,
    waiting_execution,
):
    repository.get_by_id_for_update = AsyncMock(
        return_value=waiting_execution
    )

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_99",
    )

    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_for_resume_wrong_operation(
    repository,
    db,
    waiting_execution,
):
    waiting_execution.plan["tasks"][1]["operation"] = "remove_item"

    repository.get_by_id_for_update = AsyncMock(
        return_value=waiting_execution
    )

    result = await repository.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )

    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_for_update_uses_row_lock(
    repository,
    db,
    waiting_execution,
):
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = waiting_execution

    db.execute.return_value = query_result

    result = await repository.get_by_id_for_update(
        execution_id=10,
        user_id=5,
    )

    assert result is waiting_execution

    db.execute.assert_awaited_once()

    statement = db.execute.await_args.args[0]

    # Verify that SELECT ... FOR UPDATE was constructed.
    assert statement._for_update_arg is not None



@pytest.mark.asyncio
async def test_get_for_user_success(
    repository,
    db,
    waiting_execution,
):
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = waiting_execution
    db.execute.return_value = query_result

    result = await repository.get_for_user(
        execution_id=10,
        user_id=5,
    )

    assert result is waiting_execution

    db.execute.assert_awaited_once()

    statement = db.execute.await_args.args[0]

    # Both execution ID and user ID must be part of the query.
    assert len(statement._where_criteria) == 2
    assert set(statement.compile().params.values()) == {10, 5}


@pytest.mark.asyncio
async def test_get_for_user_not_found_or_wrong_owner(
    repository,
    db,
):
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = None
    db.execute.return_value = query_result

    result = await repository.get_for_user(
        execution_id=10,
        user_id=999,
    )

    assert result is None
    db.execute.assert_awaited_once()