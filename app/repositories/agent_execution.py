from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_execution import AgentExecution, ExecutionStatus


class AgentExecutionRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_user(
        self,
        *,
        execution_id: int,
        user_id: int,
    ) -> AgentExecution | None:
        statement = select(AgentExecution).where(
            AgentExecution.id == execution_id,
            AgentExecution.user_id == user_id,
        )

        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def claim_for_resume(
        self,
        *,
        execution_id: int,
        user_id: int,
        waiting_task_id: str,
    ) -> AgentExecution | None:
        """
        Atomically claim a waiting execution for approval resumption.

        Only a valid waiting place_order task can be claimed.
        """

        execution = await self.get_by_id_for_update(
            execution_id=execution_id,
            user_id=user_id,
        )

        if execution is None:
            return None

        if execution.status != ExecutionStatus.WAITING_FOR_APPROVAL.value:
            return None

        if execution.waiting_task_id != waiting_task_id:
            return None

        # Validate persisted plan.
        plan = execution.plan

        if not isinstance(plan, dict):
            return None

        tasks = plan.get("tasks")

        if not isinstance(tasks, list) or not tasks:
            return None

        # Ensure task IDs are valid and unique.
        task_ids = []

        for task in tasks:
            if not isinstance(task, dict):
                return None

            task_id = task.get("id")

            if not isinstance(task_id, str) or not task_id:
                return None

            task_ids.append(task_id)

        if len(task_ids) != len(set(task_ids)):
            return None

        if waiting_task_id not in task_ids:
            return None

        waiting_task = next(
            task for task in tasks
            if task["id"] == waiting_task_id
        )

        if waiting_task.get("operation") != "place_order":
            return None

        # Validate persisted task statuses.
        task_statuses = execution.task_statuses

        if not isinstance(task_statuses, dict):
            return None

        # Every planned task must have exactly one persisted status.
        if set(task_statuses.keys()) != set(task_ids):
            return None

        allowed_statuses = {
            "pending",
            "running",
            "succeeded",
            "failed",
            "skipped",
            "waiting_for_approval",
            "rejected",
            "expired",
        }

        if not all(
            status in allowed_statuses
            for status in task_statuses.values()
        ):
            return None

        # The requested task must actually be waiting.
        if task_statuses.get(waiting_task_id) != "waiting_for_approval":
            return None

        # No task should still be executing when we resume.
        if "running" in task_statuses.values():
            return None

        # Claim execution only after all validations pass.
        execution.status = ExecutionStatus.RESUMING.value

        await self.db.flush()

        return execution


    async def get_by_id_for_update(
        self,
        execution_id: int,
        user_id: int,
    ) -> AgentExecution | None:
        statement = (
            select(AgentExecution)
            .where(
                AgentExecution.id == execution_id,
                AgentExecution.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(statement)
        return result.scalar_one_or_none()



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