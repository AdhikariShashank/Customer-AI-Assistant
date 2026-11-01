from fastapi import APIRouter, Depends, Query

from app.models.user import User
from app.security import require_admin
from app.routers.dependencies import get_approval_service

from app.services.approval import ApprovalService
from app.schemas.common import SuccessResponse
from app.schemas.approval import ApprovalResponse, ApprovalReviewRequest

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["Approvals"],
)


@router.get(
    "/pending",
    response_model=SuccessResponse[list[ApprovalResponse]],
)
async def list_pending_approvals(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(require_admin),
    service: ApprovalService = Depends(get_approval_service),
):
    approvals = await service.get_pending_approvals(
        limit=limit,
        offset=offset,
    )

    return SuccessResponse(
        data=[
            ApprovalResponse.model_validate(approval)
            for approval in approvals
        ],
        message="Pending approval requests fetched successfully",
    )


@router.get(
    "/{approval_id}",
    response_model=SuccessResponse[ApprovalResponse],
)
async def get_approval(
    approval_id: int,
    current_admin: User = Depends(require_admin),
    service: ApprovalService = Depends(get_approval_service),
):
    approval = await service.get_request(
        approval_id=approval_id,
    )

    return SuccessResponse(
        data=ApprovalResponse.model_validate(approval),
        message="Approval request fetched successfully",
    )

@router.post(
    "/{approval_id}/approve",
    response_model=SuccessResponse[ApprovalResponse],
)
async def approve_request(
    approval_id: int,
    request: ApprovalReviewRequest,
    current_admin: User = Depends(require_admin),
    service: ApprovalService = Depends(get_approval_service),
):
    approval = await service.approve(
        approval_id=approval_id,
        reviewer_id=current_admin.id,
        comment=request.comment,
    )

    return SuccessResponse(
        data=ApprovalResponse.model_validate(approval),
        message="Approval request approved successfully",
    )


@router.post(
    "/{approval_id}/reject",
    response_model=SuccessResponse[ApprovalResponse],
)
async def reject_request(
    approval_id: int,
    request: ApprovalReviewRequest,
    current_admin: User = Depends(require_admin),
    service: ApprovalService = Depends(get_approval_service),
):
    approval = await service.reject(
        approval_id=approval_id,
        reviewer_id=current_admin.id,
        comment=request.comment,
    )

    return SuccessResponse(
        data=ApprovalResponse.model_validate(approval),
        message="Approval request rejected successfully",
    )