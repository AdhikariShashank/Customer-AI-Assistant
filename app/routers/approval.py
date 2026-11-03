from fastapi import APIRouter, Depends, Query, Request

from app.models.approval_request import ApprovalStatus
from app.models.user import User
from app.security import require_admin
from app.routers.dependencies import get_approval_service

from app.services.approval import ApprovalService
from app.schemas.common import SuccessResponse
from app.schemas.approval import ApprovalResponse, ApprovalReviewRequest
from app.tools.dependencies import approval_service_context

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
    request: Request,
    review_request: ApprovalReviewRequest,
    current_admin: User = Depends(require_admin),
):
    operation_registry = request.app.state.operation_registry
    executor = request.app.state.executor

    # Phase 1: Approve and commit.
    async with approval_service_context(
        operation_registry=operation_registry,
    ) as service:
        approval = await service.approve(
            approval_id=approval_id,
            reviewer_id=current_admin.id,
            comment=review_request.comment,
        )

    # Approval transaction is committed here.

    if approval.status == ApprovalStatus.EXPIRED.value:
        return SuccessResponse(
            data=ApprovalResponse.model_validate(approval),
            message="Approval request has expired.",
        )

    if approval.status == ApprovalStatus.APPROVED.value:
        # Phase 2: Resume the waiting execution.
        outcome = await executor.resume(
            execution_id=approval.execution_id,
            user_id=approval.user_id,
            approval_id=approval.id,
            waiting_task_id=approval.waiting_task_id,
        )

        return SuccessResponse(
            data=ApprovalResponse.model_validate(approval),
            message=(
                "Approval successful. "
                f"Execution status: {outcome['execution_status']}"
            ),
        )

    return SuccessResponse(
        data=ApprovalResponse.model_validate(approval),
        message="Approval request processed.",
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

    message = (
        "Approval request has expired."
        if approval.status == ApprovalStatus.EXPIRED.value
        else "Approval request rejected successfully"
    )

    return SuccessResponse(
        data=ApprovalResponse.model_validate(approval),
        message=message,
    )


@router.post(
    "/expire",
    response_model=SuccessResponse[dict],
)
async def expire_pending_approvals(
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    service: ApprovalService = Depends(get_approval_service),
):
    result = await service.expire_pending_approvals(
        limit=limit,
    )

    return SuccessResponse(
        data=result,
        message="Expired approval requests processed successfully",
    )