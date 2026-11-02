
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_request import ApprovalStatus
from app.repositories.approval import ApprovalRepository
from app.repositories.agent_execution import AgentExecutionRepository
from app.schemas.approval import ExpirationResult
from app.services.execution_resolution import ExecutionResolutionService

logger = logging.getLogger(__name__)


class ApprovalExpirationService:
    """Expires pending approvals and resolves their associated executions."""

    def __init__(
        self,
        db: AsyncSession,
        approval_repository: ApprovalRepository,
        execution_repository: AgentExecutionRepository,
        operation_registry: dict,
    ) -> None:
        self.db = db
        self.approval_repository = approval_repository
        self.execution_repository = execution_repository

        self.execution_resolution_service = ExecutionResolutionService(
            execution_repository=execution_repository,
            operation_registry=operation_registry,
        )

    async def expire_pending_approvals(
        self,
        batch_size: int = 100,
    ) -> ExpirationResult:
        """
        Process a batch of expired pending approvals.

        Each approval is processed inside a savepoint so that one
        failure does not roll back the other approvals in the batch.

        The caller owns the outer transaction and must commit it.
        """

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        now = datetime.now(timezone.utc)

        approvals = (
            await self.approval_repository.get_expired_pending_for_update(
                now=now,
                limit=batch_size,
            )
        )

        logger.info(
            "Starting approval expiration batch. "
            "batch_size=%s found_count=%s",
            batch_size,
            len(approvals),
        )

        expired_count = 0
        failed_count = 0

        for approval in approvals:
            try:
                async with self.db.begin_nested():
                    await self._expire_one(
                        approval=approval,
                    )

                expired_count += 1

                logger.info(
                    "Approval expired successfully. "
                    "approval_id=%s execution_id=%s",
                    approval.id,
                    approval.execution_id,
                )

            except Exception:
                failed_count += 1

                logger.exception(
                    "Failed to expire approval. "
                    "approval_id=%s execution_id=%s",
                    approval.id,
                    approval.execution_id,
                )

        result = ExpirationResult(
            processed_count=len(approvals),
            expired_count=expired_count,
            failed_count=failed_count,
            skipped_count=0,
        )

        logger.info(
            "Approval expiration batch completed. "
            "processed=%s expired=%s failed=%s",
            result.processed_count,
            result.expired_count,
            result.failed_count,
        )

        return result

    async def _expire_one(
        self,
        approval,
    ) -> None:
        """Expire one approval and resolve its waiting execution."""

        if approval.status != ApprovalStatus.PENDING.value:
            raise ValueError(
                f"Approval {approval.id} is not pending."
            )

        if approval.execution_id is None:
            raise ValueError(
                f"Approval {approval.id} has no associated execution."
            )

        if not approval.waiting_task_id:
            raise ValueError(
                f"Approval {approval.id} has no waiting task ID."
            )

        # Lock the associated execution in the same transaction.
        execution = (
            await self.execution_repository.get_by_id_for_update(
                approval.execution_id
            )
        )

        if execution is None:
            raise ValueError(
                f"Execution {approval.execution_id} "
                f"for approval {approval.id} was not found."
            )

        # Update the approval and execution in the same savepoint.
        await self.approval_repository.mark_expired(approval)

        await self.execution_resolution_service.resolve_approval(
            execution=execution,
            task_id=approval.waiting_task_id,
            outcome="expired",
            approval_id=approval.id,
        )
