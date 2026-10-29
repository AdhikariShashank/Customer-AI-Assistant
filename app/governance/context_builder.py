import logging
from typing import AsyncContextManager, Callable

from app.governance.schemas import PolicyContext
from app.services.order import OrderService


logger = logging.getLogger(__name__)


OrderServiceContextFactory = Callable[
    [],
    AsyncContextManager[OrderService],
]


class GovernanceContextBuilder:
    """Enrich a task context with trusted backend facts."""

    def __init__(
        self,
        order_service_context: OrderServiceContextFactory,
    ) -> None:
        self.order_service_context = order_service_context

    async def build(
        self,
        context: PolicyContext,
    ) -> PolicyContext:
        """Return a context enriched with operation-specific facts."""

        logger.debug(
            "governance.context_build_started operation=%s user_id=%s",
            context.operation,
            context.user_id,
        )

        # Other operations do not need checkout facts for this policy.
        if context.operation != "place_order":
            logger.debug(
                "governance.context_build_skipped "
                "reason=operation_not_applicable operation=%s",
                context.operation,
            )
            return context

        # This ID must come from trusted runtime configuration,
        # never from planner-generated arguments.
        if context.user_id is None or context.user_id < 1:
            logger.warning(
                "governance.checkout_facts_skipped "
                "reason=invalid_trusted_user_id operation=%s",
                context.operation,
            )
            return context.model_copy(
                update={
                    "attributes": {
                        **context.attributes,
                    }
                }
            )

        logger.debug(
            "governance.checkout_facts_retrieval_started "
            "operation=%s user_id=%s",
            context.operation,
            context.user_id,
        )

        try:
            async with self.order_service_context() as service:
                facts = await service.get_checkout_facts(
                    user_id=context.user_id,
                )
        except Exception:
            logger.exception(
                "governance.checkout_facts_retrieval_failed "
                "operation=%s user_id=%s",
                context.operation,
                context.user_id,
            )
            # Fail closed: do not silently continue with incomplete
            # checkout context if the backend lookup fails.
            raise

        attributes = dict(context.attributes)

        # If facts are unavailable, leave the required facts absent.
        # The high-value policy must fail closed when it cannot
        # determine the order total.
        if facts is None:
            logger.warning(
                "governance.checkout_facts_unavailable "
                "operation=%s user_id=%s "
                "existing_attribute_count=%s",
                context.operation,
                context.user_id,
                len(attributes),
            )
        else:
            attributes.update(facts)

            logger.info(
                "governance.checkout_facts_retrieved "
                "operation=%s user_id=%s "
                "fact_count=%s attribute_count=%s",
                context.operation,
                context.user_id,
                len(facts),
                len(attributes),
            )

        enriched_context = context.model_copy(
            update={"attributes": attributes}
        )

        logger.debug(
            "governance.context_build_completed "
            "operation=%s user_id=%s "
            "checkout_facts_available=%s",
            context.operation,
            context.user_id,
            facts is not None,
        )

        return enriched_context