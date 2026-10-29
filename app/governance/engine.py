import logging

from app.governance.registry import PolicyRegistry
from app.governance.schemas import (
    GovernanceDecision,
    GovernanceResult,
    PolicyContext,
    PolicyResult,
)

logger = logging.getLogger(__name__)


class GovernanceEngine:
    """Evaluates policies and produces a final decision."""

    def __init__(self, registry: PolicyRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: PolicyContext) -> GovernanceResult:
        operation = context.operation

        logger.debug(
            "governance.evaluation_started operation=%s task_id=%s",
            operation,
            context.task_id,
        )

        policies = self.registry.policies_for(operation)
        required_ids = self.registry.required_policy_ids(operation)
        is_governed = self.registry.is_governed(operation)

        logger.debug(
            "governance.policies_loaded operation=%s "
            "is_governed=%s policy_count=%s required_policy_count=%s",
            operation,
            is_governed,
            len(policies),
            len(required_ids),
        )

        # An operation explicitly governed but with no registered policy
        # must not proceed.
        if is_governed and not policies:
            logger.error(
                "governance.no_registered_policies operation=%s",
                operation,
            )
            return self._failure(
                operation=operation,
                reason_code="GOVERNANCE_POLICY_MISSING",
            )

        registered_ids = {
            getattr(policy, "__policy_id__", None)
            for policy in policies
        }

        missing_ids = required_ids - registered_ids

        if missing_ids:
            logger.error(
                "governance.required_policies_missing "
                "operation=%s missing_policy_ids=%s",
                operation,
                sorted(missing_ids),
            )
            return self._failure(
                operation=operation,
                reason_code="GOVERNANCE_REQUIRED_POLICY_MISSING",
                evaluated_policy_ids=sorted(registered_ids - {None}),
            )

        results: list[PolicyResult] = []
        evaluated_ids: list[str] = []
        matched_ids: list[str] = []

        try:
            for policy in policies:
                policy_id = getattr(policy, "__policy_id__", None)

                if policy_id is None:
                    logger.error(
                        "governance.policy_id_missing operation=%s "
                        "evaluated_policy_ids=%s",
                        operation,
                        evaluated_ids,
                    )
                    return self._failure(
                        operation=operation,
                        reason_code="GOVERNANCE_POLICY_ID_MISSING",
                        evaluated_policy_ids=evaluated_ids,
                    )

                logger.debug(
                    "governance.policy_evaluation_started "
                    "operation=%s task_id=%s policy_id=%s",
                    operation,
                    context.task_id,
                    policy_id,
                )

                evaluated_ids.append(policy_id)
                result = policy(context)

                # None means the policy ran but did not restrict this task.
                if result is None:
                    logger.debug(
                        "governance.policy_not_applicable "
                        "operation=%s task_id=%s policy_id=%s",
                        operation,
                        context.task_id,
                        policy_id,
                    )
                    continue

                if result.policy_id != policy_id:
                    logger.error(
                        "governance.policy_id_mismatch "
                        "operation=%s expected_policy_id=%s "
                        "actual_policy_id=%s",
                        operation,
                        policy_id,
                        result.policy_id,
                    )
                    return self._failure(
                        operation=operation,
                        reason_code="GOVERNANCE_POLICY_ID_MISMATCH",
                        evaluated_policy_ids=evaluated_ids,
                    )

                results.append(result)
                matched_ids.append(policy_id)

                logger.info(
                    "governance.policy_evaluated "
                    "operation=%s task_id=%s policy_id=%s "
                    "decision=%s reason_code=%s",
                    operation,
                    context.task_id,
                    policy_id,
                    result.decision.value,
                    result.reason_code,
                )

        except Exception:
            logger.exception(
                "governance.policy_evaluation_failed "
                "operation=%s task_id=%s evaluated_policy_ids=%s",
                operation,
                context.task_id,
                evaluated_ids,
            )
            return self._failure(
                operation=operation,
                reason_code="GOVERNANCE_EVALUATION_FAILED",
                evaluated_policy_ids=evaluated_ids,
                matched_policy_ids=matched_ids,
                policy_results=results,
            )

        decisions = {result.decision for result in results}

        if GovernanceDecision.DENY in decisions:
            final_decision = GovernanceDecision.DENY
        elif GovernanceDecision.REQUIRE_APPROVAL in decisions:
            final_decision = GovernanceDecision.REQUIRE_APPROVAL
        else:
            final_decision = GovernanceDecision.ALLOW

        reason_codes = list(
            dict.fromkeys(result.reason_code for result in results)
        )

        logger.info(
            "governance.evaluation_completed "
            "operation=%s task_id=%s decision=%s "
            "evaluated_policy_count=%s matched_policy_count=%s "
            "reason_codes=%s",
            operation,
            context.task_id,
            final_decision.value,
            len(evaluated_ids),
            len(matched_ids),
            reason_codes,
        )

        return GovernanceResult(
            decision=final_decision,
            reason_codes=reason_codes,
            matched_policy_ids=matched_ids,
            evaluated_policy_ids=evaluated_ids,
            policy_results=results,
        )

    @staticmethod
    def _failure(
        *,
        operation: str,
        reason_code: str,
        evaluated_policy_ids: list[str] | None = None,
        matched_policy_ids: list[str] | None = None,
        policy_results: list[PolicyResult] | None = None,
    ) -> GovernanceResult:
        logger.error(
            "governance.evaluation_blocked "
            "operation=%s reason_code=%s",
            operation,
            reason_code,
        )

        return GovernanceResult(
            decision=GovernanceDecision.DENY,
            reason_codes=[reason_code],
            evaluated_policy_ids=evaluated_policy_ids or [],
            matched_policy_ids=matched_policy_ids or [],
            policy_results=policy_results or [],
        )