
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
        task_ids = [task.id for task in self.tasks]

        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique.")

        known_ids = set(task_ids)

        for task in self.tasks:
            if task.id in task.depends_on:
                raise ValueError(f"{task.id} cannot depend on itself.")

            unknown = set(task.depends_on) - known_ids
            if unknown:
                raise ValueError(
                    f"{task.id} references unknown tasks: {sorted(unknown)}"
                )

        return self


