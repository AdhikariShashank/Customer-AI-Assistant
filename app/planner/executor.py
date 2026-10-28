
import asyncio
import json
import logging
from pprint import pformat
from typing import Any

from app.planner.exceptions import TaskExecutionError
from app.planner.operations import OperationSpec
from app.planner.scheduler import DependencyAwareScheduler
from app.planner.schemas import OutputReference, Plan, Task


logger = logging.getLogger(__name__)


def get_output_path(value: Any, path: str) -> Any:
    """Read a dot-separated path from a dict, list, or model."""

    current = value

    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(
                    f"Output field {part!r} not found in reference path"
                )
            current = current[part]

        elif isinstance(current, (list, tuple)):
            if not part.isdigit():
                raise KeyError(
                    f"Expected a list index, got {part!r}"
                )

            index = int(part)
            current = current[index]

        else:
            # Support Pydantic models and similar objects with fields.
            if hasattr(current, "model_dump"):
                current = current.model_dump()

                if part not in current:
                    raise KeyError(
                        f"Output field {part!r} not found"
                    )

                current = current[part]

            elif hasattr(current, part):
                current = getattr(current, part)

            else:
                raise KeyError(
                    f"Cannot resolve {part!r} in output path {path!r}"
                )

    return current


def resolve_input_reference(
    reference: OutputReference,
    completed_results: dict[str, Any],
) -> Any:
    """Resolve an output path and optional list-item selection."""

    if reference.task_id not in completed_results:
        raise TaskExecutionError(
            f"Referenced task {reference.task_id} has no result."
        )

    try:
        value = get_output_path(
            completed_results[reference.task_id],
            reference.path,
        )

        # Optionally find exactly one matching item in a list.
        if reference.select_by is not None:
            if not isinstance(value, (list, tuple)):
                raise TypeError(
                    f"Reference path {reference.path!r} is not a list."
                )

            field = reference.select_by["field"]
            expected_value = reference.select_by["value"]

            matches = [
                item
                for item in value
                if isinstance(item, dict)
                and item.get(field) == expected_value
            ]

            if len(matches) != 1:
                raise ValueError(
                    f"Expected one item matching "
                    f"{field}={expected_value!r}, "
                    f"found {len(matches)}."
                )

            value = matches[0]

        # Optionally extract a field from the selected item.
        if reference.select_field is not None:
            value = get_output_path(
                value,
                reference.select_field,
            )

        return value

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TaskExecutionError(
            f"Could not resolve reference from "
            f"{reference.task_id}.{reference.path}: {exc}"
        ) from exc


class SequentialExecutor:
    """Execute dependency-aware batches with parallel task execution."""

    def __init__(
        self,
        registry: dict[str, OperationSpec],
        max_batch_size: int = 5,
    ):
        self.registry = registry
        self.max_batch_size = max_batch_size

    def _resolve_arguments(
        self,
        task: Task,
        completed_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve runtime references and merge them with literal arguments."""

        resolved = dict(task.arguments)

        for argument_name, reference in task.input_refs.items():
            value = resolve_input_reference(
                reference=reference,
                completed_results=completed_results,
            )

            resolved[argument_name] = value

            logger.info(
                "planner.reference_resolved task_id=%s argument=%s "
                "source_task_id=%s source_path=%s",
                task.id,
                argument_name,
                reference.task_id,
                reference.path,
            )

        return resolved

    @staticmethod
    def _result_indicates_failure(result: Any) -> bool:
        """Recognize structured tool failures, including JSON strings."""

        if isinstance(result, dict):
            return result.get("ok") is False

        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return False

            return (
                isinstance(parsed, dict)
                and parsed.get("ok") is False
            )

        return False

    async def _execute_one(
        self,
        task: Task,
        completed_results: dict[str, Any],
    ) -> tuple[str, Any, bool]:
        """
        Execute one task independently.

        Returns:
            (task_id, result, failed)

        This method does not mutate scheduler statuses or the shared
        completed-results dictionary.
        """

        logger.info(
            "planner.task_started task_id=%s operation=%s",
            task.id,
            task.operation,
        )

        try:
            spec = self.registry[task.operation]

            logger.debug(
                "planner.task_input task_id=%s arguments=%s input_refs=%s",
                task.id,
                pformat(task.arguments, sort_dicts=False),
                pformat(task.input_refs, sort_dicts=False),
            )

            # Read references only from previously completed batches.
            arguments = self._resolve_arguments(
                task=task,
                completed_results=completed_results,
            )

            logger.debug(
                "planner.task_resolved_arguments "
                "task_id=%s arguments=%s",
                task.id,
                pformat(arguments, sort_dicts=False),
            )

            validated = spec.arguments_schema.model_validate(arguments)
            validated_arguments = validated.model_dump(mode="python")

            logger.debug(
                "planner.task_validated_arguments "
                "task_id=%s arguments=%s",
                task.id,
                pformat(validated_arguments, sort_dicts=False),
            )

            result = await spec.execute.ainvoke(validated_arguments)
            failed = self._result_indicates_failure(result)

            logger.info(
                "planner.task_output task_id=%s operation=%s "
                "output_type=%s failed=%s output=%s",
                task.id,
                task.operation,
                type(result).__name__,
                failed,
                pformat(result, sort_dicts=False),
            )

            return task.id, result, failed

        except Exception as exc:
            logger.exception(
                "planner.task_execution_exception "
                "task_id=%s operation=%s",
                task.id,
                task.operation,
            )

            return (
                task.id,
                {
                    "ok": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                True,
            )

    async def _execute_batch(
        self,
        batch: list[Task],
        completed_results: dict[str, Any],
        scheduler: DependencyAwareScheduler,
        batch_number: int,
    ) -> None:
        """Execute every task in a selected batch concurrently."""

        logger.info(
            "planner.executor_parallel_batch_started "
            "batch_number=%d task_ids=%s batch_size=%d",
            batch_number,
            [task.id for task in batch],
            len(batch),
        )

        # Each task reads completed_results but does not mutate it.
        # gather preserves result ordering relative to the input awaitables.
        outcomes = await asyncio.gather(
            *[
                self._execute_one(
                    task=task,
                    completed_results=completed_results,
                )
                for task in batch
            ]
        )

        # Only update shared results and scheduler statuses after all
        # tasks in this batch have finished.
        for task_id, result, failed in outcomes:
            completed_results[task_id] = result

            if failed:
                scheduler.mark_failed(task_id)

                logger.warning(
                    "planner.executor_reported_failure "
                    "task_id=%s operation=%s",
                    task_id,
                    scheduler.tasks[task_id].operation,
                )
            else:
                scheduler.mark_succeeded(task_id)

                logger.info(
                    "planner.executor_reported_success "
                    "task_id=%s operation=%s",
                    task_id,
                    scheduler.tasks[task_id].operation,
                )

        logger.info(
            "planner.executor_parallel_batch_finished "
            "batch_number=%d task_ids=%s statuses=%s",
            batch_number,
            [task.id for task in batch],
            scheduler.statuses,
        )

    async def execute(self, plan: Plan) -> dict[str, Any]:
        """Schedule safe batches and execute each batch concurrently."""

        logger.info(
            "planner.execution_started task_count=%d",
            len(plan.tasks),
        )

        scheduler = DependencyAwareScheduler(
            plan=plan,
            registry=self.registry,
            max_batch_size=self.max_batch_size,
        )

        results: dict[str, Any] = {}
        batch_number = 0

        logger.info(
            "planner.executor_scheduler_created task_ids=%s "
            "initial_statuses=%s prerequisites=%s",
            list(scheduler.tasks.keys()),
            scheduler.statuses,
            scheduler.prerequisites,
        )

        while True:
            logger.info(
                "planner.scheduler_requesting_next_batch "
                "completed_task_ids=%s current_statuses=%s",
                list(results.keys()),
                scheduler.statuses,
            )

            batch = scheduler.next_batch()

            if not batch:
                logger.info(
                    "planner.scheduler_finished "
                    "no_more_tasks=true final_statuses=%s",
                    scheduler.statuses,
                )
                break

            batch_number += 1

            logger.info(
                "planner.executor_batch_received batch_number=%d "
                "task_ids=%s operations=%s",
                batch_number,
                [task.id for task in batch],
                [task.operation for task in batch],
            )

            await self._execute_batch(
                batch=batch,
                completed_results=results,
                scheduler=scheduler,
                batch_number=batch_number,
            )

        # Preserve skipped-task information in the returned results.
        for task_id, status in scheduler.statuses.items():
            if status == "skipped":
                results[task_id] = {
                    "ok": False,
                    "skipped": True,
                    "error": "A prerequisite task did not succeed.",
                }

                logger.warning(
                    "planner.executor_recorded_skipped_task "
                    "task_id=%s result=%s",
                    task_id,
                    results[task_id],
                )

        logger.info(
            "planner.execution_finished task_count=%d "
            "result_count=%d final_statuses=%s total_batches=%d",
            len(plan.tasks),
            len(results),
            scheduler.statuses,
            batch_number,
        )

        logger.debug(
            "planner.execution_final_results results=%s",
            pformat(results, sort_dicts=False),
        )

        return results
