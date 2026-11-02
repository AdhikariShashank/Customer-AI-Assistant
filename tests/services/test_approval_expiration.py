
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.approval_request import ApprovalStatus
from app.services.approval_expiration import ApprovalExpirationService


@pytest.fixture
def approval_repository():
    repository = MagicMock()
    repository.get_expired_pending_for_update = AsyncMock()
    repository.mark_expired = AsyncMock()
    return repository


@pytest.fixture
def execution_repository():
    repository = MagicMock()
    repository.get_by_id_for_update = AsyncMock()
    return repository


@pytest.fixture
def db():
    session = MagicMock()
    session.begin_nested = MagicMock()
    return session


@pytest.fixture
def service(db, approval_repository, execution_repository):
    instance = ApprovalExpirationService(
        db=db,
        approval_repository=approval_repository,
        execution_repository=execution_repository,
        operation_registry={},
    )

    # Isolate this service's coordination behaviour.
    instance.execution_resolution_service.resolve_approval = AsyncMock()

    return instance


def make_approval(
    approval_id=1,
    execution_id=101,
    waiting_task_id="task_2",
    status=None,
):
    return SimpleNamespace(
        id=approval_id,
        execution_id=execution_id,
        waiting_task_id=waiting_task_id,
        status=status or ApprovalStatus.PENDING.value,
    )


def make_execution(execution_id=101):
    return SimpleNamespace(
        id=execution_id,
        status="WAITING_FOR_APPROVAL",
        waiting_task_id="task_2",
    )


def configure_savepoints(db):
    """Provide a separate savepoint context for each approval."""

    savepoint_events = []

    @asynccontextmanager
    async def savepoint():
        try:
            yield
            savepoint_events.append("released")
        except Exception:
            savepoint_events.append("rolled_back")
            raise

    db.begin_nested.side_effect = savepoint

    return savepoint_events


@pytest.mark.asyncio
async def test_rejects_invalid_batch_size(service):
    with pytest.raises(ValueError, match="batch_size must be greater than zero"):
        await service.expire_pending_approvals(batch_size=0)

    with pytest.raises(ValueError, match="batch_size must be greater than zero"):
        await service.expire_pending_approvals(batch_size=-1)


@pytest.mark.asyncio
async def test_returns_zero_counts_when_no_expired_approvals(
    service,
    approval_repository,
):
    approval_repository.get_expired_pending_for_update.return_value = []

    result = await service.expire_pending_approvals(batch_size=50)

    assert result.processed_count == 0
    assert result.expired_count == 0
    assert result.failed_count == 0
    assert result.skipped_count == 0

    approval_repository.get_expired_pending_for_update.assert_awaited_once()

    assert service.db.begin_nested.call_count == 0


@pytest.mark.asyncio
async def test_successfully_expires_approval_and_resolves_execution(
    service,
    db,
    approval_repository,
    execution_repository,
):
    approval = make_approval()
    execution = make_execution()

    approval_repository.get_expired_pending_for_update.return_value = [
        approval
    ]
    execution_repository.get_by_id_for_update.return_value = execution

    savepoint_events = configure_savepoints(db)

    result = await service.expire_pending_approvals(batch_size=10)

    assert result.processed_count == 1
    assert result.expired_count == 1
    assert result.failed_count == 0
    assert result.skipped_count == 0

    execution_repository.get_by_id_for_update.assert_awaited_once_with(101)

    approval_repository.mark_expired.assert_awaited_once_with(approval)

    service.execution_resolution_service.resolve_approval.assert_awaited_once_with(
        execution=execution,
        task_id="task_2",
        outcome="expired",
        approval_id=1,
    )

    assert savepoint_events == ["released"]


@pytest.mark.asyncio
async def test_missing_execution_fails_without_expiring_approval(
    service,
    db,
    approval_repository,
    execution_repository,
):
    approval = make_approval()

    approval_repository.get_expired_pending_for_update.return_value = [
        approval
    ]
    execution_repository.get_by_id_for_update.return_value = None

    savepoint_events = configure_savepoints(db)

    result = await service.expire_pending_approvals()

    assert result.processed_count == 1
    assert result.expired_count == 0
    assert result.failed_count == 1

    approval_repository.mark_expired.assert_not_awaited()

    service.execution_resolution_service.resolve_approval.assert_not_awaited()

    assert savepoint_events == ["rolled_back"]


@pytest.mark.asyncio
async def test_one_failed_approval_does_not_block_another(
    service,
    db,
    approval_repository,
    execution_repository,
):
    first_approval = make_approval(
        approval_id=1,
        execution_id=101,
    )
    second_approval = make_approval(
        approval_id=2,
        execution_id=102,
    )

    first_execution = make_execution(execution_id=101)
    second_execution = make_execution(execution_id=102)

    approval_repository.get_expired_pending_for_update.return_value = [
        first_approval,
        second_approval,
    ]

    execution_repository.get_by_id_for_update.side_effect = [
        first_execution,
        second_execution,
    ]

    async def resolve_execution(**kwargs):
        if kwargs["approval_id"] == 1:
            raise RuntimeError("Simulated resolution failure")

    service.execution_resolution_service.resolve_approval.side_effect = (
        resolve_execution
    )

    savepoint_events = configure_savepoints(db)

    result = await service.expire_pending_approvals(batch_size=10)

    assert result.processed_count == 2
    assert result.expired_count == 1
    assert result.failed_count == 1

    assert approval_repository.mark_expired.await_count == 2
    assert service.execution_resolution_service.resolve_approval.await_count == 2

    # First approval failed; second approval completed.
    assert savepoint_events == ["rolled_back", "released"]


@pytest.mark.asyncio
async def test_invalid_approval_is_not_processed(
    service,
    db,
    approval_repository,
    execution_repository,
):
    approval = make_approval(
        status=ApprovalStatus.APPROVED.value,
    )

    approval_repository.get_expired_pending_for_update.return_value = [
        approval
    ]

    savepoint_events = configure_savepoints(db)

    result = await service.expire_pending_approvals()

    assert result.processed_count == 1
    assert result.expired_count == 0
    assert result.failed_count == 1

    execution_repository.get_by_id_for_update.assert_not_awaited()
    approval_repository.mark_expired.assert_not_awaited()

    assert savepoint_events == ["rolled_back"]
