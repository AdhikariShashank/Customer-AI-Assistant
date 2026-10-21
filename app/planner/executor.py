
from typing import Any

from app.planner.operations import OperationSpec
from app.planner.schemas import Plan


class SequentialExecutor:
    def __init__(self, registry: dict[str, OperationSpec]):
        self.registry = registry

    async def execute(self, plan: Plan) -> dict[str, Any]:
        results: dict[str, Any] = {}

        # Phase 1 does not support runtime dependencies.
        if any(task.depends_on for task in plan.tasks):
            raise ValueError(
                "Plans with dependencies are not supported by "
                "the Phase 1 executor."
            )

        for task in plan.tasks:
            spec = self.registry.get(task.operation)

            if spec is None:
                raise ValueError(
                    f"Unsupported operation: {task.operation}"
                )

            # Validate arguments against the operation's input schema.
            validated_arguments = spec.arguments_schema.model_validate(
                task.arguments
            )

            # Convert the validated model into a dictionary for the tool.
            tool_arguments = validated_arguments.model_dump(
                mode="json"
            )

            result = await spec.execute.ainvoke(tool_arguments)

            # Require structured results for this phase.
            if not isinstance(result, dict):
                raise TypeError(
                    f"Operation '{task.operation}' returned "
                    f"{type(result).__name__}; expected dict."
                )

            results[task.id] = {
                "operation": task.operation,
                "result": result,
            }

        return results
