
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Operation = Literal[
    "search_products",
    "get_product",
    "get_active_cart",
    "add_item",
    "remove_item",
    "list_orders",
    "get_order",
    "place_order"
]


class OutputReference(BaseModel):
    """Reference to a value produced by an earlier task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(
        pattern=r"^task_[1-9][0-9]*$",
        description="ID of the task that produces the required value.",
    )

    path: list[str | int] = Field(
        min_length=1,
        description=(
            "Path to the output value, e.g. "
            '["products", 0, "id"].'
        ),
    )

class Task(BaseModel):
    """One proposed operation in an execution plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(
        pattern=r"^task_[1-9][0-9]*$",
        description="Unique task ID, e.g. task_1.",
    )
    
    operation: Operation = Field(
        description="An operation supported by the application.",
    )
    description: str = Field(
        min_length=1,
        max_length=300,
        description="A concise explanation of the task.",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments required by the selected operation.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of prerequisite tasks. Empty in basic Phase 1 plans.",
    )

    input_refs: dict[str, OutputReference] = Field(
    default_factory=dict,
    description=(
        "Mappings from argument names to outputs of prerequisite tasks."
    ),
)

    @field_validator("depends_on")
    @classmethod
    def dependencies_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate dependency IDs are not allowed.")
        return value


class Plan(BaseModel):
    """Structured plan generated from a user's request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    goal: str = Field(min_length=1, max_length=500)
    tasks: list[Task] = Field(min_length=1, max_length=20)

    
    @model_validator(mode="after")
    def validate_task_ids_and_dependencies(self):
        tasks_by_id = {task.id: task for task in self.tasks}

        if len(tasks_by_id) != len(self.tasks):
            raise ValueError("Task IDs must be unique.")

        known_ids = set(tasks_by_id)

        for task in self.tasks:
            dependencies = set(task.depends_on)

            if task.id in dependencies:
                raise ValueError(
                    f"{task.id} cannot depend on itself."
                )

            unknown = dependencies - known_ids
            if unknown:
                raise ValueError(
                    f"{task.id} references unknown dependencies: "
                    f"{sorted(unknown)}"
                )

            for argument_name, reference in task.input_refs.items():
                if argument_name in task.arguments:
                    raise ValueError(
                        f"{task.id}: '{argument_name}' cannot appear "
                        "in both arguments and input_refs."
                    )

                if reference.task_id not in known_ids:
                    raise ValueError(
                        f"{task.id} references unknown producer "
                        f"'{reference.task_id}'."
                    )

                if reference.task_id not in dependencies:
                    raise ValueError(
                        f"{task.id} must declare '{reference.task_id}' "
                        "in depends_on when referencing its output."
                    )

        # Detect cycles in the dependency graph.
        visited: set[str] = set()
        active: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in active:
                raise ValueError(
                    f"Dependency cycle detected at {task_id}."
                )

            if task_id in visited:
                return

            active.add(task_id)

            for dependency_id in tasks_by_id[task_id].depends_on:
                visit(dependency_id)

            active.remove(task_id)
            visited.add(task_id)

        for task_id in tasks_by_id:
            visit(task_id)

        return self


