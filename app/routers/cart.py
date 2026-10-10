from fastapi import APIRouter, Depends, status

from app.schemas.cart import (
    AddCartItemRequest,
    CartResponse,
    UpdateCartItemRequest,
)
from app.schemas.common import SuccessResponse
from app.services.cart import CartService
# cart.py
from app.routers.dependencies import get_cart_service
from ..security import get_current_user


router = APIRouter(
    prefix="/api/v1/cart",
    tags=["Cart"],
)


@router.get(
    "",
    response_model=SuccessResponse[CartResponse],
)
async def get_cart(
    current_user=Depends(get_current_user),
    service: CartService = Depends(get_cart_service),
):
    cart = await service.get_cart(
        user_id=current_user.id
    )

    items = []

    for item in cart.items:
        product = item.product
        unit_price = product.price

        subtotal = product.price * item.quantity

        items.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": product.name,
            "unit_price": unit_price,
            "quantity": item.quantity,
            "subtotal": subtotal
        })

    total_amount = sum(item["subtotal"] for item in items)

    return {
    "message": "Cart fetched successfully",
    "data": {
        "id": cart.id,
        "status": cart.status,
        "items": items,
        "total_amount": total_amount
    }
    }


@router.post(
    "/items",
    response_model=SuccessResponse[CartResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_cart_item(
    request: AddCartItemRequest,
    current_user=Depends(get_current_user),
    service: CartService = Depends(get_cart_service),
):
    cart = await service.add_item(
        user_id=current_user.id,
        product_id=request.product_id,
        quantity=request.quantity,
    )

    return SuccessResponse(
        data=cart,
        message="Product added to cart successfully",
    )


@router.patch(
    "/items/{item_id}",
    response_model=SuccessResponse[CartResponse],
)
async def update_cart_item(
    item_id: int,
    request: UpdateCartItemRequest,
    current_user=Depends(get_current_user),
    service: CartService = Depends(get_cart_service),
):
    cart = await service.update_item(
        user_id=current_user.id,
        item_id=item_id,
        quantity=request.quantity,
    )

    return SuccessResponse(
        data=cart,
        message="Cart item updated successfully",
    )


@router.delete(
    "/items/{item_id}",
    response_model=SuccessResponse[CartResponse],
)
async def remove_cart_item(
    item_id: int,
    current_user=Depends(get_current_user),
    service: CartService = Depends(get_cart_service),
):
    cart = await service.remove_item(
        user_id=current_user.id,
        item_id=item_id,
    )

    return SuccessResponse(
        data=cart,
        message="Product removed from cart successfully",
    )