
import pytest
from pydantic import ValidationError

from app.planner.schemas import Plan


def make_task(
    task_id,
    operation,
    *,
    arguments=None,
    input_refs=None,
    depends_on=None,
):
    return {
        "id": task_id,
        "operation": operation,
        "description": f"Test {operation}",
        "arguments": arguments or {},
        "input_refs": input_refs or {},
        "depends_on": depends_on or [],
    }


def test_valid_output_reference_is_accepted():
    plan = Plan(
        goal="Search and add a product",
        tasks=[
            make_task(
                "task_1",
                "search_products",
                arguments={"query": "keyboard", "max_price": 3000},
            ),
            make_task(
                "task_2",
                "add_item",
                arguments={"quantity": 1},
                input_refs={
                    "product_id": {
                        "task_id": "task_1",
                        "path": "products.0.id",
                    }
                },
                depends_on=["task_1"],
            ),
        ],
    )

    assert plan.tasks[1].input_refs["product_id"].task_id == "task_1"


def test_reference_requires_dependency():
    with pytest.raises(ValidationError):
        Plan(
            goal="Search and add a product",
            tasks=[
                make_task("task_1", "search_products"),
                make_task(
                    "task_2",
                    "add_item",
                    arguments={"quantity": 1},
                    input_refs={
                        "product_id": {
                            "task_id": "task_1",
                            "path": "products.0.id",
                        }
                    },
                    # Deliberately missing depends_on.
                ),
            ],
        )


def test_unknown_reference_task_is_rejected():
    with pytest.raises(ValidationError):
        Plan(
            goal="Add a product",
            tasks=[
                make_task(
                    "task_1",
                    "add_item",
                    input_refs={
                        "product_id": {
                            "task_id": "task_99",
                            "path": "id",
                        }
                    },
                    depends_on=["task_99"],
                ),
            ],
        )


def test_dependency_cycle_is_rejected():
    with pytest.raises(ValidationError):
        Plan(
            goal="Invalid cyclic plan",
            tasks=[
                make_task(
                    "task_1",
                    "search_products",
                    depends_on=["task_2"],
                ),
                make_task(
                    "task_2",
                    "get_product",
                    depends_on=["task_1"],
                ),
            ],
        )


def test_dependency_must_appear_before_dependent():
    with pytest.raises(ValidationError):
        Plan(
            goal="Incorrect task order",
            tasks=[
                make_task(
                    "task_2",
                    "add_item",
                    input_refs={
                        "product_id": {
                            "task_id": "task_1",
                            "path": "products.0.id",
                        }
                    },
                    depends_on=["task_1"],
                ),
                make_task("task_1", "search_products"),
            ],
        )
