
import json
import logging
from typing import Any
from app.planner.exceptions import TaskExecutionError
from app.planner.operations import OperationSpec
from app.planner.scheduler import DependencyAwareScheduler
from app.planner.schemas import OutputReference, Plan, Task
from pprint import pformat

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
    """Resolve a normal output path or select an item from a list."""

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

        # Optionally extract a field from the matched item.
        if reference.select_field is not None:
            value = get_output_path(value, reference.select_field)

        return value

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TaskExecutionError(
            f"Could not resolve reference from "
            f"{reference.task_id}.{reference.path}: {exc}"
        ) from exc

class SequentialExecutor:
    def __init__(self, registry: dict[str, OperationSpec]):
        self.registry = registry

    def _resolve_arguments(
        self,
        task: Task,
        completed_results: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = dict(task.arguments)

        for argument_name, reference in task.input_refs.items():
            value = resolve_input_reference(
                reference=reference,
                completed_results=completed_results,
            )

            resolved[argument_name] = value

            logger.info(
                "planner.reference_resolved task_id=%s argument=%s "
                "source_task_id=%s source_path=%s value=%r",
                task.id,
                argument_name,
                reference.task_id,
                reference.path,
                value,
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


    async def execute(self, plan: Plan) -> dict[str, Any]:
        """Schedule safe batches and execute tasks sequentially per batch."""

        logger.info(
            "planner.execution_started task_count=%d",
            len(plan.tasks),
        )

        scheduler = DependencyAwareScheduler(
            plan=plan,
            registry=self.registry,
            max_batch_size=5,
        )

        results: dict[str, Any] = {}

        logger.info(
            "planner.executor_scheduler_created task_ids=%s "
            "initial_statuses=%s prerequisites=%s",
            list(scheduler.tasks.keys()),
            scheduler.statuses,
            scheduler.prerequisites,
        )

        batch_number = 0

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

            # Stage A: tasks in the selected batch still execute sequentially.
            for position, task in enumerate(batch, start=1):
                logger.info(
                    "planner.task_started batch_number=%d "
                    "batch_position=%d batch_size=%d "
                    "task_id=%s operation=%s dependencies=%s",
                    batch_number,
                    position,
                    len(batch),
                    task.id,
                    task.operation,
                    task.depends_on,
                )

                try:
                    spec = self.registry[task.operation]

                    logger.debug(
                        "planner.task_input task_id=%s "
                        "arguments=%s input_refs=%s",
                        task.id,
                        pformat(task.arguments, sort_dicts=False),
                        pformat(task.input_refs, sort_dicts=False),
                    )

                    arguments = self._resolve_arguments(
                        task=task,
                        completed_results=results,
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

                    results[task.id] = result

                    logger.info(
                        "planner.task_output task_id=%s operation=%s "
                        "output_type=%s output=%s",
                        task.id,
                        task.operation,
                        type(result).__name__,
                        pformat(result, sort_dicts=False),
                    )

                    if self._result_indicates_failure(result):
                        scheduler.mark_failed(task.id)

                        logger.warning(
                            "planner.executor_reported_failure "
                            "task_id=%s operation=%s "
                            "scheduler_status=%s",
                            task.id,
                            task.operation,
                            scheduler.statuses[task.id],
                        )

                    else:
                        scheduler.mark_succeeded(task.id)

                        logger.info(
                            "planner.executor_reported_success "
                            "task_id=%s operation=%s "
                            "scheduler_status=%s",
                            task.id,
                            task.operation,
                            scheduler.statuses[task.id],
                        )

                except Exception as exc:
                    scheduler.mark_failed(task.id)

                    results[task.id] = {
                        "ok": False,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }

                    logger.exception(
                        "planner.task_execution_exception "
                        "task_id=%s operation=%s "
                        "scheduler_status=%s",
                        task.id,
                        task.operation,
                        scheduler.statuses[task.id],
                    )

                logger.debug(
                    "planner.executor_state_after_task "
                    "task_id=%s current_statuses=%s result_task_ids=%s",
                    task.id,
                    pformat(scheduler.statuses, sort_dicts=False),
                    list(results.keys()),
                )

            logger.info(
                "planner.executor_batch_finished batch_number=%d "
                "task_ids=%s current_statuses=%s",
                batch_number,
                [task.id for task in batch],
                scheduler.statuses,
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
            "result_count=%d final_statuses=%s",
            "total_batches=%d ",
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

