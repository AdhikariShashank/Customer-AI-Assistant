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
