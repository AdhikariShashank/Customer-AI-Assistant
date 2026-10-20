
from pydantic import ValidationError

from app.planner.schemas import Plan, Task
from app.planner.operations import OperationSpec


class PlanValidationError(ValueError):
    """Raised when a generated plan cannot safely be accepted."""


def validate_task_arguments(
    task: Task,
    registry: dict[str, OperationSpec],
) -> dict:
    spec = registry.get(task.operation)

    if spec is None:
        raise PlanValidationError(
            f"Unsupported operation: {task.operation}"
        )

    try:
        validated = spec.arguments_schema.model_validate(task.arguments)
    except ValidationError as exc:
        raise PlanValidationError(
            f"Invalid arguments for {task.operation}: {exc}"
        ) from exc

    return validated.model_dump(mode="json")


def validate_plan(
    plan: Plan,
    registry: dict[str, OperationSpec],
) -> Plan:
    """Validate all task arguments before any task is executed."""

    validated_tasks = []

    for task in plan.tasks:
        normalized_arguments = validate_task_arguments(task, registry)

        validated_tasks.append(
            task.model_copy(
                update={"arguments": normalized_arguments}
            )
        )

    return plan.model_copy(update={"tasks": validated_tasks})
