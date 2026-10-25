
import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: str = Field(
        pattern=r"^task_[1-9][0-9]*$",
        description="ID of the task producing the required value.",
    )
    path: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Dot-separated path to a value in the task result, "
            "e.g. products.0.id"
        ),
    )

    # Optional: match one item in a list by a field and value.
    select_by: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional selector with 'field' and 'value' keys "
            "for matching exactly one item in a list."
        ),
    )

    # Optional: extract a field from the matched item.
    select_field: str | None = Field(
        default=None,
        min_length=1,
        description="Field path to extract from the matched item.",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        parts = value.split(".")

        if any(not part for part in parts):
            raise ValueError("Reference path contains an empty segment.")

        for part in parts:
            if part.isdigit():
                continue

            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
                raise ValueError(f"Invalid reference path segment: {part}")

        return value


class Task(BaseModel):
    """One proposed operation in an execution plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^task_[1-9][0-9]*$")
    operation: Operation
    description: str = Field(min_length=1, max_length=300)

    # Values already known during planning.
    arguments: dict[str, Any] = Field(default_factory=dict)

    # Tool arguments populated from prior task results.
    input_refs: dict[str, OutputReference] = Field(
        default_factory=dict,
        description=(
            "Maps a tool argument name to a value produced by another task."
        ),
    )

    # All task prerequisites, including those implied by input_refs.
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("depends_on")
    @classmethod
    def dependencies_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate dependency IDs are not allowed.")
        return value

    @model_validator(mode="after")
    def validate_argument_mapping(self):
        overlap = set(self.arguments) & set(self.input_refs)

        if overlap:
            raise ValueError(
                "Arguments cannot be both literal and referenced: "
                f"{sorted(overlap)}"
            )

        return self


class Plan(BaseModel):
    """Structured plan generated from a user's request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    goal: str = Field(min_length=1, max_length=500)
    tasks: list[Task] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_task_ids_and_dependencies(self):
        task_ids = [task.id for task in self.tasks]

        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique.")

        task_by_id = {task.id: task for task in self.tasks}
        known_ids = set(task_by_id)

        for task in self.tasks:
            if task.id in task.depends_on:
                raise ValueError(f"{task.id} cannot depend on itself.")

            unknown = set(task.depends_on) - known_ids
            if unknown:
                raise ValueError(
                    f"{task.id} references unknown dependencies: "
                    f"{sorted(unknown)}"
                )

            for argument_name, reference in task.input_refs.items():
                if reference.task_id not in known_ids:
                    raise ValueError(
                        f"{task.id}.{argument_name} references unknown "
                        f"task {reference.task_id}"
                    )

                if reference.task_id == task.id:
                    raise ValueError(
                        f"{task.id} cannot reference its own output."
                    )

                if reference.task_id not in task.depends_on:
                    raise ValueError(
                        f"{task.id} must include {reference.task_id} "
                        "in depends_on when referencing its output."
                    )

        # Detect cycles, including dependencies not represented by input_refs.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError(
                    f"Dependency cycle detected involving {task_id}"
                )

            if task_id in visited:
                return

            visiting.add(task_id)

            for dependency_id in task_by_id[task_id].depends_on:
                visit(dependency_id)

            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)

        # Phase 2 keeps execution sequential in plan order.
        # Require prerequisites to appear before their dependents.
        position = {task_id: i for i, task_id in enumerate(task_ids)}

        for task in self.tasks:
            for dependency_id in task.depends_on:
                if position[dependency_id] >= position[task.id]:
                    raise ValueError(
                        f"{dependency_id} must appear before {task.id} "
                        "in the Phase 2 sequential plan."
                    )

        return self
