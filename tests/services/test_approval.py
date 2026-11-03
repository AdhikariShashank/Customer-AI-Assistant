
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.models.approval_request import ApprovalStatus
from app.repositories.agent_execution import AgentExecutionRepository
from app.repositories.approval import ApprovalRepository
from app.services.approval import ApprovalService


@pytest.fixture
def approval_repository():
    return AsyncMock(spec=ApprovalRepository)


@pytest.fixture
def execution_repository():
    return AsyncMock(spec=AgentExecutionRepository)


@pytest.fixture
def service(approval_repository, execution_repository):
    return ApprovalService(
        repository=approval_repository,
        execution_repository=execution_repository,
        operation_registry={},
        approval_ttl=timedelta(minutes=30),
    )


@pytest.fixture
def valid_cart_snapshot():
    return {
        "cart_id": 101,
        "total_amount": "6500.00",
        "currency": "INR",
        "items": [
            {
                "product_id": 10,
                "quantity": 2,
                "unit_price": "3250.00",
                "subtotal": "6500.00",
            }
        ],
    }


@pytest.fixture
def approved_request(valid_cart_snapshot):
    return SimpleNamespace(
        id=50,
        user_id=5,
        cart_id=101,
        operation="place_order",
        status=ApprovalStatus.APPROVED.value,
        requested_amount=Decimal("6500.00"),
        currency="INR",
        cart_snapshot=valid_cart_snapshot,
        execution_id=20,
        waiting_task_id="task_3",
    )


@pytest.mark.asyncio
async def test_get_approved_request_success(
    service,
    approval_repository,
    approved_request,
):
    approval_repository.get_by_id.return_value = approved_request

    result = await service.get_approved_request(
        approval_id=50,
        user_id=5,
        execution_id=20,
        waiting_task_id="task_3",
    )

    assert result is approved_request

    approval_repository.get_by_id.assert_awaited_once_with(
        approval_id=50,
    )


@pytest.mark.asyncio
async def test_get_approved_request_not_found(
    service,
    approval_repository,
):
    approval_repository.get_by_id.return_value = None

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=5,
            execution_id=20,
            waiting_task_id="task_3",
        )

    assert exc_info.value.code == "APPROVAL_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_approved_request_wrong_user(
    service,
    approval_repository,
    approved_request,
):
    approval_repository.get_by_id.return_value = approved_request

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=99,
            execution_id=20,
            waiting_task_id="task_3",
        )

    assert exc_info.value.code == "APPROVAL_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_get_approved_request_not_approved(
    service,
    approval_repository,
    approved_request,
):
    approved_request.status = ApprovalStatus.PENDING.value
    approval_repository.get_by_id.return_value = approved_request

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=5,
            execution_id=20,
            waiting_task_id="task_3",
        )

    assert exc_info.value.code == "APPROVAL_NOT_APPROVED"


@pytest.mark.asyncio
async def test_get_approved_request_execution_mismatch(
    service,
    approval_repository,
    approved_request,
):
    approval_repository.get_by_id.return_value = approved_request

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=5,
            execution_id=999,
            waiting_task_id="task_3",
        )

    assert exc_info.value.code == "APPROVAL_EXECUTION_MISMATCH"


@pytest.mark.asyncio
async def test_get_approved_request_task_mismatch(
    service,
    approval_repository,
    approved_request,
):
    approval_repository.get_by_id.return_value = approved_request

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=5,
            execution_id=20,
            waiting_task_id="task_99",
        )

    assert exc_info.value.code == "APPROVAL_TASK_MISMATCH"


@pytest.mark.asyncio
async def test_get_approved_request_unsupported_operation(
    service,
    approval_repository,
    approved_request,
):
    approved_request.operation = "delete_product"
    approval_repository.get_by_id.return_value = approved_request

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=5,
            execution_id=20,
            waiting_task_id="task_3",
        )

    assert exc_info.value.code == "APPROVAL_OPERATION_UNSUPPORTED"


@pytest.mark.asyncio
async def test_get_approved_request_invalid_snapshot(
    service,
    approval_repository,
    approved_request,
):
    approved_request.cart_snapshot = None
    approval_repository.get_by_id.return_value = approved_request

    with pytest.raises(AppException) as exc_info:
        await service.get_approved_request(
            approval_id=50,
            user_id=5,
            execution_id=20,
            waiting_task_id="task_3",
        )

    assert exc_info.value.code == "INVALID_CHECKOUT_FACTS"
