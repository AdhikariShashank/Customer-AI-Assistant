
from typing import Any

from app.planner.operations import OperationSpec
from app.planner.schemas import Plan


class SequentialExecutor:
    def __init__(self, registry: dict[str, OperationSpec]):
        self.registry = registry

    async def execute(self, plan: Plan) -> dict[str, Any]:
        results = {}

        # Phase 1 deliberately does not resolve runtime dependencies.
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

            # LangChain tool instances expose ainvoke().
            # The tool's factory/closure retains trusted context.
            result = await spec.execute.ainvoke(task.arguments)

            results[task.id] = {
                "operation": task.operation,
                "result": result,
            }

        return results
