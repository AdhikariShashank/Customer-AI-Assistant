from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from psycopg import IntegrityError
import pytest

from app.core.exceptions import AppException
from app.models.approval_request import ApprovalStatus
from app.services.approval import ApprovalService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_repository():
    repository = AsyncMock()
    return repository


@pytest.fixture
def approval_service(mock_repository):
    return ApprovalService(repository=mock_repository)


@pytest.fixture
def checkout_facts():
    return {
        "cart_id": 25,
        "order_total": Decimal("6000.00"),
        "currency": "INR",
        "cart_snapshot": {
            "cart_id": 25,
            "items": [
                {
                    "product_id": 10,
                    "product_name": "Keyboard",
                    "quantity": 2,
                    "unit_price": "3000.00",
                    "subtotal": "6000.00",
                }
            ],
            "total_amount": "6000.00",
            "currency": "INR",
        },
    }


@pytest.mark.anyio
async def test_create_approval_request_success(
    approval_service,
    mock_repository,
    checkout_facts,
):
    mock_repository.get_pending_by_cart.return_value = None

    mock_repository.create.return_value = SimpleNamespace(
        id=101,
        user_id=1,
        cart_id=25,
        status=ApprovalStatus.PENDING.value,
    )

    result = await approval_service.create_request(
        user_id=1,
        checkout_facts=checkout_facts,
        policy_id="high_value_order_policy",
        reason_code="HIGH_VALUE_ORDER",
    )

    assert result.id == 101
    assert result.status == "PENDING"

    mock_repository.get_pending_by_cart.assert_awaited_once_with(25)

    mock_repository.create.assert_awaited_once()

    created_request = mock_repository.create.await_args.args[0]

    assert created_request.user_id == 1
    assert created_request.cart_id == 25
    assert created_request.operation == "place_order"
    assert created_request.requested_amount == Decimal("6000.00")
    assert created_request.currency == "INR"
    assert created_request.policy_id == "high_value_order_policy"
    assert created_request.reason_code == "HIGH_VALUE_ORDER"
    assert created_request.status == "PENDING"
    assert created_request.cart_snapshot == checkout_facts["cart_snapshot"]


@pytest.mark.anyio
async def test_create_request_fails_when_cart_id_missing(
    approval_service,
    mock_repository,
):
    facts = {
        "order_total": Decimal("6000.00"),
        "currency": "INR",
        "cart_snapshot": {},
    }

    with pytest.raises(AppException):
        await approval_service.create_request(
            user_id=1,
            checkout_facts=facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    mock_repository.create.assert_not_awaited()


@pytest.mark.anyio
async def test_create_request_fails_when_snapshot_missing(
    approval_service,
    mock_repository,
):
    facts = {
        "cart_id": 25,
        "order_total": Decimal("6000.00"),
        "currency": "INR",
    }

    with pytest.raises(AppException):
        await approval_service.create_request(
            user_id=1,
            checkout_facts=facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    mock_repository.create.assert_not_awaited()


@pytest.mark.anyio
async def test_create_request_rejects_negative_amount(
    approval_service,
    mock_repository,
    checkout_facts,
):
    checkout_facts["order_total"] = Decimal("-100.00")

    with pytest.raises(AppException):
        await approval_service.create_request(
            user_id=1,
            checkout_facts=checkout_facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    mock_repository.create.assert_not_awaited()


@pytest.mark.anyio
async def test_create_request_rejects_existing_pending_request(
    approval_service,
    mock_repository,
    checkout_facts,
):
    mock_repository.get_pending_by_cart.return_value = SimpleNamespace(
        id=100,
        status="PENDING",
    )

    with pytest.raises(AppException):
        await approval_service.create_request(
            user_id=1,
            checkout_facts=checkout_facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    mock_repository.create.assert_not_awaited()


@pytest.mark.anyio
async def test_get_request_not_found(
    approval_service,
    mock_repository,
):
    mock_repository.get_by_id.return_value = None

    with pytest.raises(AppException):
        await approval_service.get_request(999)

    mock_repository.get_by_id.assert_awaited_once_with(
        approval_id=999,
    )


@pytest.mark.anyio
async def test_get_user_approvals(
    approval_service,
    mock_repository,
):
    expected = [
        SimpleNamespace(id=101),
        SimpleNamespace(id=102),
    ]

    mock_repository.get_user_approvals.return_value = expected

    result = await approval_service.get_user_approvals(
        user_id=1,
        limit=20,
        offset=0,
    )

    assert result == expected

    mock_repository.get_user_approvals.assert_awaited_once_with(
        user_id=1,
        limit=20,
        offset=0,
    )

@pytest.mark.anyio
async def test_create_request_rejects_snapshot_amount_mismatch(
    approval_service,
    mock_repository,
    checkout_facts,
):
    checkout_facts["cart_snapshot"]["total_amount"] = "4000.00"

    with pytest.raises(AppException) as exc:
        await approval_service.create_request(
            user_id=1,
            checkout_facts=checkout_facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    assert exc.value.code == "INVALID_CHECKOUT_FACTS"
    mock_repository.create.assert_not_awaited()

@pytest.mark.anyio
async def test_create_request_rejects_snapshot_cart_mismatch(
    approval_service,
    mock_repository,
    checkout_facts,
):
    checkout_facts["cart_snapshot"]["cart_id"] = 999

    with pytest.raises(AppException) as exc:
        await approval_service.create_request(
            user_id=1,
            checkout_facts=checkout_facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    assert exc.value.code == "INVALID_CHECKOUT_FACTS"
    mock_repository.create.assert_not_awaited()

@pytest.mark.anyio
async def test_create_request_rejects_snapshot_currency_mismatch(
    approval_service,
    mock_repository,
    checkout_facts,
):
    checkout_facts["cart_snapshot"]["currency"] = "USD"

    with pytest.raises(AppException) as exc:
        await approval_service.create_request(
            user_id=1,
            checkout_facts=checkout_facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    assert exc.value.code == "INVALID_CHECKOUT_FACTS"
    mock_repository.create.assert_not_awaited()

@pytest.mark.anyio
async def test_create_request_handles_integrity_error(
    approval_service,
    mock_repository,
    checkout_facts,
):
    mock_repository.get_pending_by_cart.return_value = None

    mock_repository.create.side_effect = IntegrityError(
        "INSERT",
        {},
        Exception("duplicate pending approval"),
    )

    with pytest.raises(AppException) as exc:
        await approval_service.create_request(
            user_id=1,
            checkout_facts=checkout_facts,
            policy_id="high_value_order_policy",
            reason_code="HIGH_VALUE_ORDER",
        )

    assert exc.value.code == "APPROVAL_ALREADY_PENDING"

