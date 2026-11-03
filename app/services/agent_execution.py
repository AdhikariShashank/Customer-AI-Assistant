from typing import Any

from app.models.agent_execution import (
    AgentExecution,
    ExecutionStatus,
)
from app.repositories.agent_execution import (
    AgentExecutionRepository,
)


class AgentExecutionService:

    def __init__(
        self,
        repository: AgentExecutionRepository,
    ):
        self.repository = repository

    async def get_execution_for_user(
        self,
        *,
        execution_id: int,
        user_id: int,
    ) -> AgentExecution | None:
        """Fetch an execution only if it belongs to the given user."""

        return await self.repository.get_for_user(
            execution_id=execution_id,
            user_id=user_id,
        )

    async def claim_for_resume(
        self,
        *,
        execution_id: int,
        user_id: int,
        waiting_task_id: str,
    ) -> AgentExecution:
        """Claim a waiting execution for approval resumption."""

        execution = await self.repository.claim_for_resume(
            execution_id=execution_id,
            user_id=user_id,
            waiting_task_id=waiting_task_id,
        )

        if execution is None:
            raise ValueError(
                "Execution cannot be claimed for resumption. "
                "It may not exist, may belong to another user, "
                "or may no longer be waiting for this task's approval."
            )

        return execution

    async def create_execution(
        self,
        *,
        user_id: int,
        plan: dict[str, Any],
        results: dict[str, Any],
        task_statuses: dict[str, str],
        status: str,
        waiting_task_id: str | None = None,
    ) -> AgentExecution:

        return await self.repository.create(
            user_id=user_id,
            plan=plan,
            results=results,
            task_statuses=task_statuses,
            status=status,
            waiting_task_id=waiting_task_id,
        )

    
    async def update_execution(
        self,
        *,
        execution_id: int,
        results: dict[str, Any],
        task_statuses: dict[str, str],
        status: str,
        waiting_task_id: str | None = None,
    ) -> AgentExecution:

        execution = await self.repository.get_by_id(execution_id)

        if execution is None:
            raise ValueError(
                f"Agent execution with id={execution_id} was not found."
            )

        return await self.repository.update_state(
            execution,
            results=results,
            task_statuses=task_statuses,
            status=status,
            waiting_task_id=waiting_task_id,
        )
