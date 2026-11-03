import logging
from pprint import pformat
from typing import Literal

from app.planner.exceptions import TaskExecutionError
from app.planner.operations import OperationSpec
from app.planner.schemas import Plan, Task

logger = logging.getLogger(__name__)

TaskStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "waiting_for_approval",
    "rejected",
    "expired",
]

ALLOWED_STATUSES = {
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "waiting_for_approval",
    "rejected",
    "expired",
}


class DependencyAwareScheduler:
    """Select ready, safe batches without executing operations."""

    def __init__(
        self,
        plan: Plan,
        registry: dict[str, OperationSpec],
        max_batch_size: int = 5,
        statuses: dict[str, TaskStatus] | None = None,
    ) -> None:
        logger.info(
            "planner.scheduler_creation_started max_batch_size=%d",
            max_batch_size,
        )

        if max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1.")

        self.registry = registry
        self.max_batch_size = max_batch_size

        self.tasks: dict[str, Task] = {}
        self.statuses: dict[str, TaskStatus] = {}
        self.prerequisites: dict[str, set[str]] = {}

        logger.debug(
            "planner.scheduler_initial_plan task_count=%d plan=%s",
            len(plan.tasks),
            pformat(
                [task.model_dump(mode="python") for task in plan.tasks],
                sort_dicts=False,
            ),
        )

        self._initialize(plan)

        if statuses is not None:
            self.restore_statuses(statuses)

        self._log_state("initialization_complete")

    def resolve_approved(self, task_id: str) -> None:
        """Make an approved task eligible for execution again."""

        self._validate_task_id(task_id)

        current_status = self.statuses[task_id]

        if current_status != "waiting_for_approval":
            raise TaskExecutionError(
                f"Task {task_id!r} cannot be approved "
                f"from status {current_status!r}."
            )

        dependencies = self.prerequisites[task_id]

        unfinished_dependencies = [
            dependency
            for dependency in dependencies
            if self.statuses[dependency] != "succeeded"
        ]

        if unfinished_dependencies:
            raise TaskExecutionError(
                f"Cannot resume task {task_id!r}. "
                f"Unfinished dependencies: {unfinished_dependencies}"
            )

        self.statuses[task_id] = "pending"

        logger.info(
            "planner.scheduler_approval_resolved "
            "task_id=%s previous_status=%s new_status=pending "
            "validated_dependencies=%s",
            task_id,
            current_status,
            sorted(dependencies),
        )

        self._log_state(
            event=f"approval_resolved:{task_id}"
        )
    
    
    def resolve_approval(
        self,
        task_id: str,
        outcome: Literal["rejected", "expired"],
    ) -> list[str]:
        """Resolve an approval task and skip newly blocked tasks."""

        self._validate_task_id(task_id)

        current_status = self.statuses[task_id]

        if current_status != "waiting_for_approval":
            raise TaskExecutionError(
                f"Task {task_id} is not waiting for approval. "
                f"Current status: {current_status}"
            )

        if outcome not in ("rejected", "expired"):
            raise ValueError(f"Unsupported approval outcome: {outcome}")

        previous_statuses = self.statuses.copy()

        self.statuses[task_id] = outcome

        logger.info(
            "planner.approval_task_resolution_started "
            "task_id=%s previous_status=%s outcome=%s",
            task_id,
            current_status,
            outcome,
        )

        self._skip_blocked_tasks()

        newly_skipped = [
            dependent_id
            for dependent_id, status in self.statuses.items()
            if status == "skipped"
            and previous_statuses[dependent_id] != "skipped"
        ]

        logger.info(
            "planner.approval_task_resolution_finished "
            "task_id=%s outcome=%s newly_skipped_task_ids=%s",
            task_id,
            outcome,
            newly_skipped,
        )

        return newly_skipped


    def restore_statuses(
        self,
        statuses: dict[str, TaskStatus],
    ) -> None:
        """Restore persisted statuses after validating their safety."""

        if set(statuses) != set(self.tasks):
            raise TaskExecutionError(
                "Persisted task statuses do not match the execution plan."
            )

        for task_id, status in statuses.items():
            if status not in ALLOWED_STATUSES:
                raise TaskExecutionError(
                    f"Invalid persisted status for task {task_id}: {status}"
                )

        running_tasks = [
            task_id
            for task_id, status in statuses.items()
            if status == "running"
        ]

        if running_tasks:
            logger.error(
                "planner.scheduler_restore_rejected_running_tasks "
                "task_ids=%s",
                running_tasks,
            )
            raise TaskExecutionError(
                "Cannot automatically restore execution containing "
                f"running tasks: {running_tasks}. Their side effects "
                "must be reconciled before retrying."
            )

        self.statuses = statuses.copy()

        logger.info(
            "planner.scheduler_statuses_restored statuses=%s",
            self.statuses,
        )

        self._log_state("statuses_restored")

    def export_statuses(self) -> dict[str, TaskStatus]:
        """Return a copy suitable for persistence."""

        return self.statuses.copy()

    def mark_waiting_for_approval(self, task_id: str) -> None:
        self._validate_task_id(task_id)

        previous_status = self.statuses[task_id]
        self.statuses[task_id] = "waiting_for_approval"

        logger.info(
            "planner.scheduler_task_status_updated "
            "task_id=%s previous_status=%s new_status=%s",
            task_id,
            previous_status,
            self.statuses[task_id],
        )

        self._log_state(
            f"after_task_waiting_for_approval:{task_id}"
        )

    def mark_succeeded(self, task_id: str) -> None:
        self._validate_task_id(task_id)

        previous_status = self.statuses[task_id]
        self.statuses[task_id] = "succeeded"

        logger.info(
            "planner.scheduler_task_status_updated "
            "task_id=%s previous_status=%s new_status=%s",
            task_id,
            previous_status,
            self.statuses[task_id],
        )

        self._log_state(f"after_task_succeeded:{task_id}")

    def mark_failed(self, task_id: str) -> None:
        self._validate_task_id(task_id)

        previous_status = self.statuses[task_id]
        self.statuses[task_id] = "failed"

        logger.warning(
            "planner.scheduler_task_status_updated "
            "task_id=%s previous_status=%s new_status=%s",
            task_id,
            previous_status,
            self.statuses[task_id],
        )

        self._log_state(f"after_task_failed:{task_id}")

    def mark_skipped(self, task_id: str) -> None:
        self._validate_task_id(task_id)

        previous_status = self.statuses[task_id]
        self.statuses[task_id] = "skipped"

        logger.warning(
            "planner.scheduler_task_status_updated "
            "task_id=%s previous_status=%s new_status=%s",
            task_id,
            previous_status,
            self.statuses[task_id],
        )

        self._log_state(f"after_task_skipped:{task_id}")

    def _validate_task_id(self, task_id: str) -> None:
        if task_id not in self.statuses:
            raise TaskExecutionError(
                f"Unknown task ID: {task_id}"
            )

    def _log_state(self, event: str) -> None:
        logger.debug(
            "planner.scheduler_state event=%s "
            "tasks=%s statuses=%s prerequisites=%s",
            event,
            pformat(
                {
                    task_id: task.model_dump(mode="python")
                    for task_id, task in self.tasks.items()
                },
                sort_dicts=False,
            ),
            pformat(self.statuses, sort_dicts=False),
            pformat(
                {
                    task_id: sorted(dependencies)
                    for task_id, dependencies in self.prerequisites.items()
                },
                sort_dicts=False,
            ),
        )

    def _initialize(self, plan: Plan) -> None:
        logger.info(
            "planner.scheduler_building_task_lookup task_count=%d",
            len(plan.tasks),
        )

        for task in plan.tasks:
            if task.id in self.tasks:
                raise TaskExecutionError(
                    f"Duplicate task ID: {task.id}"
                )

            if task.operation not in self.registry:
                raise TaskExecutionError(
                    f"Unsupported operation: {task.operation}"
                )

            self.tasks[task.id] = task
            self.statuses[task.id] = "pending"

            logger.debug(
                "planner.scheduler_task_registered "
                "task_id=%s operation=%s status=%s "
                "arguments=%s depends_on=%s input_refs=%s access=%s",
                task.id,
                task.operation,
                self.statuses[task.id],
                pformat(task.arguments, sort_dicts=False),
                task.depends_on,
                pformat(task.input_refs, sort_dicts=False),
                self.registry[task.operation].access,
            )

        logger.info(
            "planner.scheduler_task_lookup_built task_count=%d",
            len(self.tasks),
        )

        for task in plan.tasks:
            prerequisites = set(task.depends_on)

            reference_dependencies = {
                reference.task_id
                for reference in task.input_refs.values()
            }

            prerequisites.update(reference_dependencies)

            if task.id in prerequisites:
                raise TaskExecutionError(
                    f"Task {task.id} cannot depend on itself."
                )

            unknown = prerequisites - set(self.tasks)

            if unknown:
                raise TaskExecutionError(
                    f"Task {task.id} references unknown tasks: "
                    f"{sorted(unknown)}"
                )

            self.prerequisites[task.id] = prerequisites

            logger.debug(
                "planner.scheduler_prerequisites_registered "
                "task_id=%s prerequisites=%s",
                task.id,
                sorted(prerequisites),
            )

        self._validate_acyclic()

        logger.info(
            "planner.scheduler_initialized task_count=%d "
            "max_batch_size=%d",
            len(self.tasks),
            self.max_batch_size,
        )

    def _validate_acyclic(self) -> None:
        logger.info("planner.scheduler_cycle_validation_started")

        remaining = {
            task_id: set(dependencies)
            for task_id, dependencies in self.prerequisites.items()
        }

        completed: set[str] = set()

        while True:
            ready = {
                task_id
                for task_id, dependencies in remaining.items()
                if task_id not in completed
                and dependencies.issubset(completed)
            }

            if not ready:
                break

            completed.update(ready)

        if len(completed) != len(self.tasks):
            unresolved = sorted(set(self.tasks) - completed)

            logger.error(
                "planner.scheduler_cycle_validation_failed "
                "unresolved_tasks=%s",
                unresolved,
            )

            raise TaskExecutionError(
                "Dependency cycle detected among tasks: "
                f"{unresolved}"
            )

        logger.info(
            "planner.scheduler_cycle_validation_succeeded "
            "validated_task_count=%d",
            len(completed),
        )

    def _skip_blocked_tasks(self) -> None:
        """Skip pending tasks whose prerequisites failed or were skipped."""

        changed = True

        while changed:
            changed = False

            for task_id, dependencies in self.prerequisites.items():
                if self.statuses[task_id] != "pending":
                    continue

                failed_dependencies = [
                    dependency
                    for dependency in dependencies
                    if self.statuses[dependency] in (
                        "failed",
                        "skipped",
                        "rejected",
                        "expired",
                    )
                ]

                if failed_dependencies:
                    self.statuses[task_id] = "skipped"
                    changed = True

                    logger.warning(
                        "planner.task_skipped task_id=%s "
                        "failed_dependencies=%s",
                        task_id,
                        failed_dependencies,
                    )

        self._log_state("after_blocked_task_check")

    def _get_ready_tasks(self) -> list[Task]:
        ready_tasks = [
            task
            for task_id, task in self.tasks.items()
            if self.statuses[task_id] == "pending"
            and all(
                self.statuses[dependency] == "succeeded"
                for dependency in self.prerequisites[task_id]
            )
        ]

        logger.debug(
            "planner.scheduler_ready_tasks "
            "ready_task_ids=%s ready_operations=%s",
            [task.id for task in ready_tasks],
            [task.operation for task in ready_tasks],
        )

        return ready_tasks

    def next_batch(self) -> list[Task]:
        """Select the next safe batch and mark its tasks as running."""

        logger.info("planner.scheduler_next_batch_started")

        self._log_state("before_next_batch")
        self._skip_blocked_tasks()

        pending = [
            task_id
            for task_id, status in self.statuses.items()
            if status == "pending"
        ]

        if not pending:
            logger.info(
                "planner.scheduler_no_pending_tasks "
                "all_tasks_terminal_or_waiting=true"
            )
            self._log_state("execution_finished")
            return []

        ready = self._get_ready_tasks()

        if not ready:
            waiting_tasks = [
                task_id
                for task_id, status in self.statuses.items()
                if status == "waiting_for_approval"
            ]

            if waiting_tasks:
                logger.info(
                    "planner.scheduler_paused_for_approval "
                    "waiting_tasks=%s pending_tasks=%s",
                    waiting_tasks,
                    pending,
                )
                return []

            raise TaskExecutionError(
                "Pending tasks remain, but no tasks are ready: "
                f"{pending}"
            )

        ready_reads = [
            task
            for task in ready
            if self.registry[task.operation].access == "read"
        ]

        if ready_reads:
            batch = ready_reads[: self.max_batch_size]

            logger.info(
                "planner.scheduler_batch_policy "
                "reason=ready_read_operations"
            )
        else:
            # Serialize writes to avoid concurrent write side effects.
            batch = [ready[0]]

            logger.info(
                "planner.scheduler_batch_policy "
                "reason=serialize_write_operations"
            )

        for task in batch:
            self.statuses[task.id] = "running"

        logger.info(
            "planner.batch_selected task_ids=%s operations=%s",
            [task.id for task in batch],
            [task.operation for task in batch],
        )

        self._log_state("after_batch_selected")

        return batch