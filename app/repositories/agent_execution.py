from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_execution import AgentExecution


class AgentExecutionRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        plan: dict[str, Any],
        results: dict[str, Any],
        task_statuses: dict[str, str],
        status: str,
        waiting_task_id: str | None = None,
    ) -> AgentExecution:

        execution = AgentExecution(
            user_id=user_id,
            plan=plan,
            results=results,
            task_statuses=task_statuses,
            status=status,
            waiting_task_id=waiting_task_id,
        )

        self.db.add(execution)
        await self.db.flush()
        await self.db.refresh(execution)

        return execution

    async def get_by_id(
        self,
        execution_id: int,
    ) -> AgentExecution | None:

        result = await self.db.execute(
            select(AgentExecution).where(
                AgentExecution.id == execution_id
            )
        )

        return result.scalar_one_or_none()

    async def update_state(
        self,
        execution: AgentExecution,
        *,
        results: dict[str, Any],
        task_statuses: dict[str, str],
        status: str,
        waiting_task_id: str | None = None,
    ) -> AgentExecution:

        execution.results = results
        execution.task_statuses = task_statuses
        execution.status = status
        execution.waiting_task_id = waiting_task_id

        await self.db.flush()
        await self.db.refresh(execution)

        return execution