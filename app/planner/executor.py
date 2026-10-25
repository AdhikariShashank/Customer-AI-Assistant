
import logging
from typing import Any

from pydantic import ValidationError

from app.planner.operations import OperationSpec
from app.planner.schemas import OutputReference, Plan, Task
from pprint import pformat

logger = logging.getLogger(__name__)


class TaskExecutionError(RuntimeError):
    """Raised when a task cannot be executed safely."""


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

    async def execute(self, plan: Plan) -> dict[str, Any]:
        """Execute tasks sequentially, respecting validated dependencies."""

        results: dict[str, Any] = {}

        logger.info(
            "planner.execution_started task_count=%d",
            len(plan.tasks),
        )

        for task in plan.tasks:
            logger.info(
                "planner.task_started task_id=%s operation=%s "
                "dependencies=%s",
                task.id,
                task.operation,
                task.depends_on,
            )

            spec = self.registry.get(task.operation)

            if spec is None:
                raise TaskExecutionError(
                    f"Unsupported operation: {task.operation}"
                )

            missing_dependencies = [
                dependency
                for dependency in task.depends_on
                if dependency not in results
            ]

            if missing_dependencies:
                raise TaskExecutionError(
                    f"Task {task.id} cannot execute before "
                    f"dependencies {missing_dependencies}"
                )

            try:

                logger.info(
                    "planner.task_input task_id=%s arguments=%r input_refs=%r",
                    task.id,
                    task.arguments,
                    task.input_refs,
                )
                arguments = self._resolve_arguments(task, results)

                logger.info(
                    "planner.task_arguments_resolved task_id=%s arguments=%r",
                    task.id,
                    arguments,
                )

                # Validate the final arguments, including resolved values.
                validated = spec.arguments_schema.model_validate(arguments)
                validated_arguments = validated.model_dump(mode="python")

                result = await spec.execute.ainvoke(validated_arguments)

                logger.info(
                    "\n========== TOOL OUTPUT ==========\n"
                    "Task ID: %s\n"
                    "Operation: %s\n"
                    "Output type: %s\n"
                    "Actual output:\n%s\n"
                    "=================================",
                    task.id,
                    task.operation,
                    type(result).__name__,
                    pformat(result, sort_dicts=False),
                )

                logger.info(
                    "planner.task_executed operation=%s result=%s",
                    task.operation,
                    result,
                )

                # Store the raw tool result for downstream references.
                results[task.id] = result

                logger.info(
                    "planner.results_updated task_id=%s current_results=%s",
                    task.id,
                    results,
                )

                logger.info(
                    "planner.task_succeeded task_id=%s operation=%s",
                    task.id,
                    task.operation,
                )

            except (ValidationError, TaskExecutionError):
                logger.exception(
                    "planner.task_failed task_id=%s operation=%s",
                    task.id,
                    task.operation,
                )
                raise

            except Exception:
                logger.exception(
                    "planner.task_failed task_id=%s operation=%s",
                    task.id,
                    task.operation,
                )
                raise

        logger.info("planner.execution_succeeded task_count=%d", len(results))

        return results
