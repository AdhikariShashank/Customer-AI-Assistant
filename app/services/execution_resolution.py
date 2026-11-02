
import logging
from copy import deepcopy
from typing import Literal

from app.models.agent_execution import AgentExecution
from app.planner.exceptions import TaskExecutionError
from app.planner.operations import OperationSpec
from app.planner.scheduler import DependencyAwareScheduler
from app.planner.schemas import Plan

logger = logging.getLogger(__name__)


class ExecutionResolutionService:
    """Resolves executions paused for approval."""

    def __init__(
        self,
        execution_repository,
        operation_registry: dict[str, OperationSpec],
    ) -> None:
        self.execution_repository = execution_repository
        self.operation_registry = operation_registry

    async def resolve_approval(
        self,
        *,
        execution: AgentExecution,
        task_id: str,
        outcome: Literal["rejected", "expired"],
        approval_id: int,
    ) -> AgentExecution:
        """
        Resolve the waiting task and persist the execution state.

        The caller must provide an execution already locked
        inside the current database transaction.
        """

        execution_status = str(
            getattr(execution.status, "value", execution.status)
        ).upper()

        if execution_status != "WAITING_FOR_APPROVAL":
            raise TaskExecutionError(
                f"Execution {execution.id} is not waiting for approval. "
                f"Current status: {execution_status}"
            )

        if execution.waiting_task_id != task_id:
            raise TaskExecutionError(
                f"Execution {execution.id} is waiting for task "
                f"{execution.waiting_task_id}, not {task_id}."
            )

        if outcome not in ("rejected", "expired"):
            raise ValueError(f"Unsupported outcome: {outcome}")

        plan = Plan.model_validate(execution.plan)

        scheduler = DependencyAwareScheduler(
            plan=plan,
            registry=self.operation_registry,
            statuses=execution.task_statuses,
        )

        skipped_task_ids = scheduler.resolve_approval(
            task_id=task_id,
            outcome=outcome,
        )

        results = deepcopy(execution.results or {})

        error_code = (
            "APPROVAL_REJECTED"
            if outcome == "rejected"
            else "APPROVAL_EXPIRED"
        )

        error_message = (
            "The administrator rejected this operation."
            if outcome == "rejected"
            else "The approval request expired before it was reviewed."
        )

        results[task_id] = {
            "success": False,
            "error": {
                "code": error_code,
                "message": error_message,
            },
            "approval": {
                "approval_id": approval_id,
                "status": outcome,
            },
        }

        for skipped_task_id in skipped_task_ids:

            results[skipped_task_id] = {
                "success": False,
                "status": "skipped",
                "message": (
                    f"Task skipped because prerequisite task "
                    f"{task_id} was {outcome}."
                ),
            }

        updated_execution = (
            await self.execution_repository.update_state(
                execution,
                results=results,
                task_statuses=scheduler.export_statuses(),
                status="FAILED",
                waiting_task_id=None,
            )
        )

        logger.info(
            "execution.approval_resolution_completed "
            "execution_id=%s approval_id=%s task_id=%s "
            "outcome=%s skipped_task_ids=%s",
            execution.id,
            approval_id,
            task_id,
            outcome,
            skipped_task_ids,
        )

        return updated_execution
