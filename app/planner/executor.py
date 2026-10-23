
import logging
from typing import Any

from pydantic import ValidationError

from app.planner.operations import OperationSpec
from app.planner.schemas import Plan, Task

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
            if reference.task_id not in completed_results:
                raise TaskExecutionError(
                    f"Task {task.id} requires {reference.task_id}, "
                    "but that task has no successful result."
                )

            try:
                value = get_output_path(
                    completed_results[reference.task_id],
                    reference.path,
                )
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise TaskExecutionError(
                    f"Could not resolve {task.id}.{argument_name} "
                    f"from {reference.task_id}.{reference.path}"
                ) from exc

            resolved[argument_name] = value

            logger.info(
                "planner.reference_resolved task_id=%s argument=%s "
                "source_task_id=%s source_path=%s value_type=%s",
                task.id,
                argument_name,
                reference.task_id,
                reference.path,
                type(value).__name__,
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
                    "planner.task_executed operation=%s result=%s",
                    task.operation,
                    result,
                )

                # Store the raw tool result for downstream references.
                results[task.id] = result

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
