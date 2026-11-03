
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.agent_execution import ExecutionStatus
from app.repositories.agent_execution import AgentExecutionRepository
from app.services.agent_execution import AgentExecutionService


@pytest.fixture
def repository():
    return AsyncMock(spec=AgentExecutionRepository)


@pytest.fixture
def service(repository):
    return AgentExecutionService(repository=repository)


@pytest.mark.asyncio
async def test_claim_for_resume_success(service, repository):
    """A valid waiting execution should be returned."""

    execution = SimpleNamespace(
        id=10,
        user_id=5,
        status=ExecutionStatus.RESUMING.value,
        waiting_task_id="task_3",
    )

    repository.claim_for_resume.return_value = execution

    result = await service.claim_for_resume(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )

    assert result is execution

    repository.claim_for_resume.assert_awaited_once_with(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )


@pytest.mark.asyncio
async def test_claim_for_resume_execution_not_claimable(
    service,
    repository,
):
    """The service should raise when the repository returns None."""

    repository.claim_for_resume.return_value = None

    with pytest.raises(
        ValueError,
        match="Execution cannot be claimed for resumption",
    ):
        await service.claim_for_resume(
            execution_id=10,
            user_id=5,
            waiting_task_id="task_3",
        )

    repository.claim_for_resume.assert_awaited_once_with(
        execution_id=10,
        user_id=5,
        waiting_task_id="task_3",
    )


@pytest.mark.asyncio
async def test_claim_for_resume_passes_correct_arguments(
    service,
    repository,
):
    """The authenticated user and waiting task must be forwarded."""

    execution = SimpleNamespace(id=20)
    repository.claim_for_resume.return_value = execution

    await service.claim_for_resume(
        execution_id=20,
        user_id=7,
        waiting_task_id="task_5",
    )

    repository.claim_for_resume.assert_awaited_once_with(
        execution_id=20,
        user_id=7,
        waiting_task_id="task_5",
    )



@pytest.mark.asyncio
async def test_get_execution_for_user_success(
    service,
    repository,
):
    execution = SimpleNamespace(
        id=10,
        user_id=5,
    )

    repository.get_for_user.return_value = execution

    result = await service.get_execution_for_user(
        execution_id=10,
        user_id=5,
    )

    assert result is execution

    repository.get_for_user.assert_awaited_once_with(
        execution_id=10,
        user_id=5,
    )


@pytest.mark.asyncio
async def test_get_execution_for_user_not_found(
    service,
    repository,
):
    repository.get_for_user.return_value = None

    result = await service.get_execution_for_user(
        execution_id=10,
        user_id=999,
    )

    assert result is None

    repository.get_for_user.assert_awaited_once_with(
        execution_id=10,
        user_id=999,
    )