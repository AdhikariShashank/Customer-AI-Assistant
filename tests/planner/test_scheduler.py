
import pytest
from types import SimpleNamespace

from app.planner.exceptions import TaskExecutionError
from app.planner.scheduler import DependencyAwareScheduler
from app.planner.schemas import Plan, Task


@pytest.fixture
def scheduler():
    """Create a scheduler with two independent tasks."""

    tasks = [
        Task.model_construct(
            id="task_1",
            operation="get_products",
            arguments={},
            depends_on=[],
            input_refs={},
        ),
        Task.model_construct(
            id="task_2",
            operation="get_cart",
            arguments={},
            depends_on=[],
            input_refs={},
        ),
    ]

    plan = Plan.model_construct(tasks=tasks)

    # The scheduler only needs the operation's access attribute.
    registry = {
        "get_products": SimpleNamespace(access="read"),
        "get_cart": SimpleNamespace(access="read"),
    }

    return DependencyAwareScheduler(
        plan=plan,
        registry=registry,
        max_batch_size=5,
    )


@pytest.fixture
def dependent_scheduler():
    """Create a scheduler where task_2 depends on task_1."""

    tasks = [
        Task.model_construct(
            id="task_1",
            operation="get_products",
            arguments={},
            depends_on=[],
            input_refs={},
        ),
        Task.model_construct(
            id="task_2",
            operation="get_cart",
            arguments={},
            depends_on=["task_1"],
            input_refs={},
        ),
    ]

    plan = Plan.model_construct(tasks=tasks)

    registry = {
        "get_products": SimpleNamespace(access="read"),
        "get_cart": SimpleNamespace(access="read"),
    }

    return DependencyAwareScheduler(
        plan=plan,
        registry=registry,
        max_batch_size=5,
    )


# --------------------------------------------------
# APPROVAL RESUMPTION TESTS
# --------------------------------------------------


def test_resolve_approved_task_becomes_pending(scheduler):
    scheduler.statuses["task_2"] = "waiting_for_approval"

    scheduler.resolve_approved("task_2")

    assert scheduler.statuses["task_2"] == "pending"


def test_resolve_approved_task_becomes_ready(scheduler):
    scheduler.statuses["task_1"] = "succeeded"
    scheduler.statuses["task_2"] = "waiting_for_approval"

    scheduler.resolve_approved("task_2")

    batch = scheduler.next_batch()

    assert "task_2" in [task.id for task in batch]
    assert scheduler.statuses["task_2"] == "running"


def test_resolve_approved_task_with_succeeded_dependency(
    dependent_scheduler,
):
    dependent_scheduler.statuses["task_1"] = "succeeded"
    dependent_scheduler.statuses["task_2"] = "waiting_for_approval"

    dependent_scheduler.resolve_approved("task_2")

    assert dependent_scheduler.statuses["task_2"] == "pending"

    batch = dependent_scheduler.next_batch()

    assert [task.id for task in batch] == ["task_2"]
    assert dependent_scheduler.statuses["task_2"] == "running"


def test_resolve_approved_task_rejects_pending_dependency(
    dependent_scheduler,
):
    dependent_scheduler.statuses["task_1"] = "pending"
    dependent_scheduler.statuses["task_2"] = "waiting_for_approval"

    with pytest.raises(TaskExecutionError):
        dependent_scheduler.resolve_approved("task_2")

    assert dependent_scheduler.statuses["task_2"] == "waiting_for_approval"


def test_resolve_approved_task_rejects_failed_dependency(
    dependent_scheduler,
):
    dependent_scheduler.statuses["task_1"] = "failed"
    dependent_scheduler.statuses["task_2"] = "waiting_for_approval"

    with pytest.raises(TaskExecutionError):
        dependent_scheduler.resolve_approved("task_2")

    assert dependent_scheduler.statuses["task_2"] == "waiting_for_approval"


def test_resolve_approved_task_rejects_invalid_status(scheduler):
    scheduler.statuses["task_2"] = "succeeded"

    with pytest.raises(TaskExecutionError):
        scheduler.resolve_approved("task_2")


def test_resolve_approved_task_rejects_unknown_task(scheduler):
    with pytest.raises(TaskExecutionError):
        scheduler.resolve_approved("task_999")


# --------------------------------------------------
# REJECTION AND EXPIRY TESTS
# --------------------------------------------------


@pytest.mark.parametrize("outcome", ["rejected", "expired"])
def test_resolve_approval_updates_task_status(scheduler, outcome):
    scheduler.statuses["task_2"] = "waiting_for_approval"

    newly_skipped = scheduler.resolve_approval(
        task_id="task_2",
        outcome=outcome,
    )

    assert scheduler.statuses["task_2"] == outcome
    assert newly_skipped == []


def test_rejected_task_skips_dependent_tasks(dependent_scheduler):
    dependent_scheduler.statuses["task_1"] = "waiting_for_approval"

    newly_skipped = dependent_scheduler.resolve_approval(
        task_id="task_1",
        outcome="rejected",
    )

    assert dependent_scheduler.statuses["task_1"] == "rejected"
    assert dependent_scheduler.statuses["task_2"] == "skipped"
    assert newly_skipped == ["task_2"]


def test_expired_task_skips_dependent_tasks(dependent_scheduler):
    dependent_scheduler.statuses["task_1"] = "waiting_for_approval"

    newly_skipped = dependent_scheduler.resolve_approval(
        task_id="task_1",
        outcome="expired",
    )

    assert dependent_scheduler.statuses["task_1"] == "expired"
    assert dependent_scheduler.statuses["task_2"] == "skipped"
    assert newly_skipped == ["task_2"]


def test_resolve_approval_rejects_invalid_outcome(scheduler):
    scheduler.statuses["task_2"] = "waiting_for_approval"

    with pytest.raises(ValueError):
        scheduler.resolve_approval(
            task_id="task_2",
            outcome="approved",
        )


def test_resolve_approval_rejects_non_waiting_task(scheduler):
    scheduler.statuses["task_2"] = "pending"

    with pytest.raises(TaskExecutionError):
        scheduler.resolve_approval(
            task_id="task_2",
            outcome="rejected",
        )
