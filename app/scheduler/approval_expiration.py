
import logging

from app.db import AsyncLocalSession
from app.repositories.approval import ApprovalRepository
from app.repositories.agent_execution import AgentExecutionRepository
from app.services.approval_expiration import ApprovalExpirationService
from app.planner.operations import OPERATION_REGISTRY

logger = logging.getLogger(__name__)


async def run_approval_expiration_batch(
    batch_size: int = 100,
) -> None:
    """Run one approval-expiration batch."""

    async with AsyncLocalSession() as db:
        try:
            approval_repository = ApprovalRepository(db)
            execution_repository = AgentExecutionRepository(db)

            service = ApprovalExpirationService(
                db=db,
                approval_repository=approval_repository,
                execution_repository=execution_repository,
                operation_registry=OPERATION_REGISTRY,
            )

            result = await service.expire_pending_approvals(
                batch_size=batch_size,
            )

            await db.commit()

            logger.info(
                "Approval expiration worker committed batch. "
                "processed=%s expired=%s failed=%s",
                result.processed_count,
                result.expired_count,
                result.failed_count,
            )

        except Exception:
            await db.rollback()
            logger.exception(
                "Approval expiration worker batch failed."
            )
            raise
