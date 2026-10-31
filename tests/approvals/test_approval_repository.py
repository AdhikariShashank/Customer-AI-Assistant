
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.user import User
from app.models.cart import Cart
from app.models.approval_request import (
    ApprovalRequest,
    ApprovalStatus,
)
from app.repositories.approval import ApprovalRepository


# ---------------------------------------------------------
# Test Database Engine
# ---------------------------------------------------------

settings = get_settings()

test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    echo=False,
)


# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_session(anyio_backend):
    """
    Creates an isolated database transaction for each test.

    NullPool ensures that connections are not reused across
    different asyncio event loops.

    The outer transaction is rolled back after each test.
    """

    async with test_engine.connect() as connection:

        outer_transaction = await connection.begin()

        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        try:
            yield session

        finally:
            await session.close()

            if outer_transaction.is_active:
                await outer_transaction.rollback()


@pytest.fixture
async def user_and_cart(db_session):
    """
    Creates a test user and an active cart.
    """

    user = User(
        email=f"{uuid4()}@example.com",
        hashed_password="test-password",
        is_active=True,
        role="CUSTOMER",
    )

    db_session.add(user)
    await db_session.flush()

    cart = Cart(
        user_id=user.id,
        status="ACTIVE",
    )

    db_session.add(cart)
    await db_session.flush()

    return user, cart


# ---------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------

def build_approval_request(
    user_id: int,
    cart_id: int,
    status: ApprovalStatus = ApprovalStatus.PENDING,
) -> ApprovalRequest:

    now = datetime.now(timezone.utc)

    return ApprovalRequest(
        user_id=user_id,
        cart_id=cart_id,
        operation="place_order",
        status=status.value,
        policy_id="high_value_order_policy",
        reason_code="HIGH_VALUE_ORDER",
        requested_amount="6000.00",
        currency="INR",
        cart_snapshot={
            "cart_id": cart_id,
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
        expires_at=now + timedelta(hours=24),
    )


# ---------------------------------------------------------
# Repository Tests
# ---------------------------------------------------------

@pytest.mark.anyio
async def test_approval_repository_crud(
    db_session,
    user_and_cart,
):
    user, cart = user_and_cart

    repository = ApprovalRepository(db_session)

    # 1. Create approval request.
    approval = build_approval_request(
        user_id=user.id,
        cart_id=cart.id,
    )

    created = await repository.create(approval)

    assert created.id is not None
    assert created.status == ApprovalStatus.PENDING.value

    # 2. Retrieve by ID.
    fetched = await repository.get_by_id(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.user_id == user.id

    # 3. Retrieve pending request by cart.
    pending = await repository.get_pending_by_cart(cart.id)

    assert pending is not None
    assert pending.id == created.id

    # 4. Retrieve pending request with row lock.
    locked = await repository.get_pending_for_update(created.id)

    assert locked is not None
    assert locked.id == created.id

    # 5. Update review.
    reviewed = await repository.update_review(
        locked,
        status=ApprovalStatus.APPROVED,
        reviewed_by=user.id,
        reviewed_at=datetime.now(timezone.utc),
        review_comment="Approved for testing",
    )

    assert reviewed.status == ApprovalStatus.APPROVED.value
    assert reviewed.reviewed_by == user.id
    assert reviewed.review_comment == "Approved for testing"

    # 6. Approved requests should no longer appear as pending.
    pending = await repository.get_pending_by_cart(cart.id)

    assert pending is None

    # 7. Retrieve customer approval history.
    approvals = await repository.get_user_approvals(
        user_id=user.id,
    )

    assert len(approvals) == 1
    assert approvals[0].id == created.id


@pytest.mark.anyio
async def test_duplicate_pending_approval_rejected_by_database(
    db_session,
    user_and_cart,
):
    user, cart = user_and_cart

    repository = ApprovalRepository(db_session)

    first_request = build_approval_request(
        user_id=user.id,
        cart_id=cart.id,
    )

    await repository.create(first_request)

    second_request = build_approval_request(
        user_id=user.id,
        cart_id=cart.id,
    )

    # Use a savepoint so the expected database error does not
    # invalidate the outer test transaction.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repository.create(second_request)

    # The original pending request should still exist.
    pending = await repository.get_pending_by_cart(cart.id)

    assert pending is not None
    assert pending.id == first_request.id


# ---------------------------------------------------------
# Engine Cleanup
# ---------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def dispose_test_engine():
    """
    Dispose the test engine after this module's tests finish.
    """

    yield

    # Engine disposal is performed below using the current
    # event loop in an async cleanup fixture.
