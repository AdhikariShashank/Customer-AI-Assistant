
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.approval import ApprovalService


@pytest.fixture
def approval_service():
    """
    Create ApprovalService without invoking its constructor.

    These tests focus only on expiry processing, so database
    repositories and execution resolution are mocked.
    """
    service = ApprovalService.__new__(ApprovalService)

    service.repository = SimpleNamespace(
        get_expired_pending_for_update=AsyncMock(),
        mark_expired=AsyncMock(),
    )

    service._resolve_execution = AsyncMock()

    return service


@pytest.mark.asyncio
async def test_expire_pending_approvals_when_no_expired_records(
    approval_service,
):
    approval_service.repository.get_expired_pending_for_update.return_value = []

    result = await approval_service.expire_pending_approvals()

    assert result == {
        "processed_count": 0,
        "expired_approval_ids": [],
    }

    approval_service.repository.get_expired_pending_for_update.assert_awaited_once()

    approval_service.repository.mark_expired.assert_not_awaited()
    approval_service._resolve_execution.assert_not_awaited()


@pytest.mark.asyncio
async def test_expire_single_pending_approval(approval_service):
    approval = SimpleNamespace(id=101)

    approval_service.repository.get_expired_pending_for_update.return_value = [
        approval
    ]

    result = await approval_service.expire_pending_approvals()

    assert result == {
        "processed_count": 1,
        "expired_approval_ids": [101],
    }

    approval_service.repository.mark_expired.assert_awaited_once_with(
        approval
    )

    approval_service._resolve_execution.assert_awaited_once_with(
        approval=approval,
        outcome="expired",
    )


@pytest.mark.asyncio
async def test_expire_multiple_pending_approvals(approval_service):
    approvals = [
        SimpleNamespace(id=101),
        SimpleNamespace(id=102),
        SimpleNamespace(id=103),
    ]

    approval_service.repository.get_expired_pending_for_update.return_value = (
        approvals
    )

    result = await approval_service.expire_pending_approvals(limit=10)

    assert result == {
        "processed_count": 3,
        "expired_approval_ids": [101, 102, 103],
    }

    assert (
        approval_service.repository.mark_expired.await_count == 3
    )

    assert (
        approval_service._resolve_execution.await_count == 3
    )

    for approval in approvals:
        approval_service.repository.mark_expired.assert_any_await(
            approval
        )

        approval_service._resolve_execution.assert_any_await(
            approval=approval,
            outcome="expired",
        )


@pytest.mark.asyncio
async def test_expiry_processing_passes_batch_limit_to_repository(
    approval_service,
):
    approval_service.repository.get_expired_pending_for_update.return_value = []

    await approval_service.expire_pending_approvals(limit=25)

    call_kwargs = (
        approval_service.repository
        .get_expired_pending_for_update
        .await_args.kwargs
    )

    assert call_kwargs["limit"] == 25

    # The service should use a timezone-aware UTC timestamp.
    assert isinstance(call_kwargs["now"], datetime)
    assert call_kwargs["now"].tzinfo is not None
    assert call_kwargs["now"].utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_expiry_processing_stops_if_mark_expired_fails(
    approval_service,
):
    approval = SimpleNamespace(id=101)

    approval_service.repository.get_expired_pending_for_update.return_value = [
        approval
    ]

    approval_service.repository.mark_expired.side_effect = RuntimeError(
        "Database update failed"
    )

    with pytest.raises(RuntimeError, match="Database update failed"):
        await approval_service.expire_pending_approvals()

    # Execution must not be resolved if marking the approval failed.
    approval_service._resolve_execution.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_processing_propagates_execution_resolution_failure(
    approval_service,
):
    approval = SimpleNamespace(id=101)

    approval_service.repository.get_expired_pending_for_update.return_value = [
        approval
    ]

    approval_service._resolve_execution.side_effect = RuntimeError(
        "Execution resolution failed"
    )

    with pytest.raises(RuntimeError, match="Execution resolution failed"):
        await approval_service.expire_pending_approvals()

    approval_service.repository.mark_expired.assert_awaited_once_with(
        approval
    )
