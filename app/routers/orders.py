
from app.routers.dependencies import get_order_service
from ..security import get_current_user

service: OrderService = Depends(get_order_service)

from fastapi import APIRouter, Depends, status

from app.schemas.common import SuccessResponse
from app.schemas.order import (
    OrderListResponse,
    OrderResponse,
)
from app.services.order import OrderService


router = APIRouter(
    prefix="/api/v1/orders",
    tags=["Orders"],
)


@router.get(
    "",
    response_model=SuccessResponse[OrderListResponse],
)
async def list_orders(
    current_user=Depends(get_current_user),
    service: OrderService = Depends(),
):
    orders, total = await service.list_orders(
        user_id=current_user.id
    )

    return SuccessResponse(
        data=OrderListResponse(
            items=orders,
            total=total,
        ),
        message="Orders fetched successfully",
    )


@router.get(
    "/{order_id}",
    response_model=SuccessResponse[OrderResponse],
)
async def get_order(
    order_id: int,
    current_user=Depends(get_current_user),
    service: OrderService = Depends(),
):
    order = await service.get_order(
        user_id=current_user.id,
        order_id=order_id,
    )

    return SuccessResponse(
        data=order,
        message="Order fetched successfully",
    )


@router.post(
    "",
    response_model=SuccessResponse[OrderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def place_order(
    current_user=Depends(get_current_user),
    service: OrderService = Depends(),
):
    order = await service.place_order(
        user_id=current_user.id
    )

    return SuccessResponse(
        data=order,
        message="Order placed successfully",
    )


@router.post(
    "/{order_id}/cancel",
    response_model=SuccessResponse[OrderResponse],
)
async def cancel_order(
    order_id: int,
    current_user=Depends(get_current_user),
    service: OrderService = Depends(),
):
    order = await service.cancel_order(
        user_id=current_user.id,
        order_id=order_id,
    )

    return SuccessResponse(
        data=order,
        message="Order cancelled successfully",
    )