import logging
from pprint import pformat
from typing import Literal

from app.planner.operations import OperationSpec
from app.planner.schemas import Plan, Task
from app.planner.exceptions import TaskExecutionError

logger = logging.getLogger(__name__)

TaskStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
]


class DependencyAwareScheduler:
    """Select ready, safe batches without executing operations."""

    def __init__(
        self,
        plan: Plan,
        registry: dict[str, OperationSpec],
        max_batch_size: int = 5,
    ):
        logger.info(
            "planner.scheduler_creation_started max_batch_size=%d",
            max_batch_size,
        )

        if max_batch_size < 1:
            logger.error(
                "planner.scheduler_invalid_batch_size max_batch_size=%d",
                max_batch_size,
            )
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
                [
                    task.model_dump(mode="python")
                    for task in plan.tasks
                ],
                sort_dicts=False,
            ),
        )

        logger.debug(
            "planner.scheduler_registry operations=%s",
            pformat(
                {
                    name: {
                        "access": spec.access,
                        "output_description": spec.output_description,
                    }
                    for name, spec in registry.items()
                },
                sort_dicts=False,
            ),
        )

        self._initialize(plan)

        self._log_state("initialization_complete")

    def _log_state(self, event: str) -> None:
        """Log the scheduler's current internal state."""

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

        # Build a task lookup and initialize task statuses.
        for task in plan.tasks:
            if task.id in self.tasks:
                logger.error(
                    "planner.scheduler_duplicate_task_id task_id=%s",
                    task.id,
                )
                raise TaskExecutionError(
                    f"Duplicate task ID: {task.id}"
                )

            if task.operation not in self.registry:
                logger.error(
                    "planner.scheduler_unsupported_operation "
                    "task_id=%s operation=%s",
                    task.id,
                    task.operation,
                )
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

        # Dependencies include explicitly declared prerequisites
        # and tasks referenced by input_refs.
        logger.info("planner.scheduler_building_prerequisites")

        for task in plan.tasks:
            prerequisites = set(task.depends_on)

            reference_dependencies = {
                reference.task_id
                for reference in task.input_refs.values()
            }

            prerequisites.update(reference_dependencies)

            logger.debug(
                "planner.scheduler_dependency_analysis "
                "task_id=%s explicit_dependencies=%s "
                "input_ref_dependencies=%s combined_dependencies=%s",
                task.id,
                sorted(task.depends_on),
                sorted(reference_dependencies),
                sorted(prerequisites),
            )

            if task.id in prerequisites:
                logger.error(
                    "planner.scheduler_self_dependency task_id=%s",
                    task.id,
                )
                raise TaskExecutionError(
                    f"Task {task.id} cannot depend on itself."
                )

            unknown = prerequisites - set(self.tasks)

            if unknown:
                logger.error(
                    "planner.scheduler_unknown_dependencies "
                    "task_id=%s unknown_dependencies=%s",
                    task.id,
                    sorted(unknown),
                )
                raise TaskExecutionError(
                    f"Task {task.id} references unknown tasks: "
                    f"{sorted(unknown)}"
                )

            self.prerequisites[task.id] = prerequisites

            logger.info(
                "planner.scheduler_prerequisites_registered "
                "task_id=%s prerequisites=%s",
                task.id,
                sorted(prerequisites),
            )

        self._log_state("before_cycle_validation")

        # Detect cycles before any operation can execute.
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
        round_number = 0

        logger.debug(
            "planner.scheduler_cycle_validation_initial_dependencies=%s",
            pformat(remaining, sort_dicts=False),
        )

        while True:
            round_number += 1

            ready = {
                task_id
                for task_id, dependencies in remaining.items()
                if task_id not in completed
                and dependencies.issubset(completed)
            }

            logger.debug(
                "planner.scheduler_cycle_validation_round "
                "round=%d completed=%s ready=%s",
                round_number,
                sorted(completed),
                sorted(ready),
            )

            if not ready:
                break

            completed.update(ready)

        if len(completed) != len(self.tasks):
            cyclic_or_blocked = sorted(
                set(self.tasks) - completed
            )

            logger.error(
                "planner.scheduler_cycle_validation_failed "
                "unresolved_tasks=%s completed_tasks=%s",
                cyclic_or_blocked,
                sorted(completed),
            )

            raise TaskExecutionError(
                "Dependency cycle detected among tasks: "
                f"{cyclic_or_blocked}"
            )

        logger.info(
            "planner.scheduler_cycle_validation_succeeded "
            "validated_task_count=%d",
            len(completed),
        )

    def _skip_blocked_tasks(self) -> None:
        """Skip pending tasks whose prerequisites failed or were skipped."""

        logger.debug("planner.scheduler_blocked_task_check_started")

        changed = True

        while changed:
            changed = False

            for task_id, dependencies in self.prerequisites.items():
                if self.statuses[task_id] != "pending":
                    continue

                failed_dependencies = [
                    dependency
                    for dependency in dependencies
                    if self.statuses[dependency]
                    in ("failed", "skipped")
                ]

                if failed_dependencies:
                    previous_status = self.statuses[task_id]
                    self.statuses[task_id] = "skipped"
                    changed = True

                    logger.warning(
                        "planner.task_skipped task_id=%s "
                        "previous_status=%s new_status=%s "
                        "failed_dependencies=%s",
                        task_id,
                        previous_status,
                        self.statuses[task_id],
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
        """Return the next safe batch, or an empty list when finished."""

        logger.info("planner.scheduler_next_batch_started")

        self._log_state("before_next_batch")

        self._skip_blocked_tasks()

        pending = [
            task_id
            for task_id, status in self.statuses.items()
            if status == "pending"
        ]

        logger.debug(
            "planner.scheduler_pending_tasks task_ids=%s",
            pending,
        )

        if not pending:
            logger.info(
                "planner.scheduler_no_pending_tasks "
                "all_tasks_terminal=true"
            )
            self._log_state("execution_finished")
            return []

        ready = self._get_ready_tasks()

        if not ready:
            logger.error(
                "planner.scheduler_no_ready_tasks "
                "pending_tasks=%s statuses=%s prerequisites=%s",
                pending,
                pformat(self.statuses, sort_dicts=False),
                pformat(self.prerequisites, sort_dicts=False),
            )

            raise TaskExecutionError(
                "Pending tasks remain, but no tasks are ready: "
                f"{pending}"
            )

        # Read-only operations can share a batch.
        ready_reads = [
            task
            for task in ready
            if self.registry[task.operation].access == "read"
        ]

        logger.debug(
            "planner.scheduler_batch_candidates "
            "ready_tasks=%s ready_reads=%s max_batch_size=%d",
            [task.id for task in ready],
            [task.id for task in ready_reads],
            self.max_batch_size,
        )

        if ready_reads:
            batch = ready_reads[: self.max_batch_size]

            logger.info(
                "planner.scheduler_batch_policy "
                "reason=ready_read_operations"
            )
        else:
            # Conservative policy: never put multiple writes in a batch.
            batch = [ready[0]]

            logger.info(
                "planner.scheduler_batch_policy "
                "reason=serialize_write_operations"
            )

        logger.info(
            "planner.batch_selected task_ids=%s operations=%s",
            [task.id for task in batch],
            [task.operation for task in batch],
        )

        for task in batch:
            previous_status = self.statuses[task.id]
            self.statuses[task.id] = "running"

            logger.debug(
                "planner.scheduler_status_changed "
                "task_id=%s previous_status=%s new_status=%s",
                task.id,
                previous_status,
                self.statuses[task.id],
            )

        self._log_state("after_batch_selected")

        return batch

    def mark_succeeded(self, task_id: str) -> None:
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