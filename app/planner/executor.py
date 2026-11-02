import asyncio
import json
import logging
from contextlib import AbstractAsyncContextManager
from pprint import pformat
from typing import Any, Callable

from app.planner.exceptions import TaskExecutionError
from app.planner.operations import OperationSpec
from app.planner.scheduler import DependencyAwareScheduler
from app.planner.schemas import OutputReference, Plan, Task

from app.governance.context_builder import GovernanceContextBuilder
from app.governance.engine import GovernanceEngine
from app.governance.schemas import GovernanceDecision, PolicyContext

from app.services.approval import ApprovalService
from app.services.agent_execution import AgentExecutionService


logger = logging.getLogger(__name__)


ApprovalServiceContextFactory = Callable[
    [],
    AbstractAsyncContextManager[ApprovalService],
]

AgentExecutionServiceContextFactory = Callable[
    [],
    AbstractAsyncContextManager[AgentExecutionService],
]


def get_output_path(value: Any, path: str) -> Any:
    """Read a dot-separated path from a dict, list, or model."""

    current = value

    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(
                    f"Output field {part!r} not found in reference path"
                )

            current = current[part]

        elif isinstance(current, (list, tuple)):
            if not part.isdigit():
                raise KeyError(
                    f"Expected a list index, got {part!r}"
                )

            current = current[int(part)]

        else:
            if hasattr(current, "model_dump"):
                current = current.model_dump()

                if part not in current:
                    raise KeyError(
                        f"Output field {part!r} not found"
                    )

                current = current[part]

            elif hasattr(current, part):
                current = getattr(current, part)

            else:
                raise KeyError(
                    f"Cannot resolve {part!r} in output path {path!r}"
                )

    return current


def resolve_input_reference(
    reference: OutputReference,
    completed_results: dict[str, Any],
) -> Any:
    """Resolve an output path and optional list-item selection."""

    if reference.task_id not in completed_results:
        raise TaskExecutionError(
            f"Referenced task {reference.task_id} has no result."
        )

    try:
        value = get_output_path(
            completed_results[reference.task_id],
            reference.path,
        )

        if reference.select_by is not None:
            if not isinstance(value, (list, tuple)):
                raise TypeError(
                    f"Reference path {reference.path!r} is not a list."
                )

            field = reference.select_by["field"]
            expected_value = reference.select_by["value"]

            matches = [
                item
                for item in value
                if isinstance(item, dict)
                and item.get(field) == expected_value
            ]

            if len(matches) != 1:
                raise ValueError(
                    f"Expected one item matching "
                    f"{field}={expected_value!r}, "
                    f"found {len(matches)}."
                )

            value = matches[0]

        if reference.select_field is not None:
            value = get_output_path(
                value,
                reference.select_field,
            )

        return value

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TaskExecutionError(
            f"Could not resolve reference from "
            f"{reference.task_id}.{reference.path}: {exc}"
        ) from exc


class SequentialExecutor:
    """Execute dependency-aware batches with governance and persistence."""

    def __init__(
        self,
        registry: dict[str, OperationSpec],
        max_batch_size: int = 5,
        governance_engine: GovernanceEngine | None = None,
        governance_context_builder: GovernanceContextBuilder | None = None,
        approval_service_context: ApprovalServiceContextFactory | None = None,
        execution_service_context: (
            AgentExecutionServiceContextFactory | None
        ) = None,
    ) -> None:
        self.registry = registry
        self.max_batch_size = max_batch_size

        self.governance_engine = governance_engine
        self.governance_context_builder = governance_context_builder

        self.approval_service_context = approval_service_context
        self.execution_service_context = execution_service_context

    # ============================================================
    # EXECUTION PERSISTENCE
    # ============================================================

    @staticmethod
    def _serialize_plan(plan: Plan) -> dict[str, Any]:
        """Convert the Pydantic plan into JSON-compatible data."""

        return plan.model_dump(mode="json")

    @staticmethod
    def _serialize_results(
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert results into JSON-compatible data.

        The default=str fallback supports values such as Decimal and
        datetime. Prefer explicitly serializable tool outputs where
        possible so reference paths retain their expected types.
        """

        return json.loads(
            json.dumps(results, default=str)
        )

    @staticmethod
    def _get_execution_status(
        statuses: dict[str, str],
    ) -> tuple[str, str | None]:
        """Derive execution status and the task awaiting approval."""

        waiting_tasks = [
            task_id
            for task_id, status in statuses.items()
            if status == "waiting_for_approval"
        ]

        if waiting_tasks:
            return "WAITING_FOR_APPROVAL", waiting_tasks[0]

        active_tasks = [
            task_id
            for task_id, status in statuses.items()
            if status in ("pending", "running")
        ]

        if active_tasks:
            return "RUNNING", None

        unsuccessful_tasks = [
            task_id
            for task_id, status in statuses.items()
            if status in ("failed", "skipped")
        ]

        if unsuccessful_tasks:
            return "FAILED", None

        return "COMPLETED", None

    async def _create_execution_record(
        self,
        plan: Plan,
        user_id: int,
        scheduler: DependencyAwareScheduler,
    ) -> int:
        """Create the durable execution record before tool execution."""

        if self.execution_service_context is None:
            raise RuntimeError(
                "Execution persistence is not configured. "
                "Provide execution_service_context."
            )

        logger.info(
            "planner.execution_record_creation_started user_id=%s",
            user_id,
        )

        async with self.execution_service_context() as service:
            execution = await service.create_execution(
                user_id=user_id,
                plan=self._serialize_plan(plan),
                results={},
                task_statuses=scheduler.export_statuses(),
                status="RUNNING",
            )

        logger.info(
            "planner.execution_record_created execution_id=%s user_id=%s",
            execution.id,
            user_id,
        )

        return execution.id

    async def _persist_execution_state(
        self,
        execution_id: int,
        results: dict[str, Any],
        scheduler: DependencyAwareScheduler,
    ) -> None:
        """Persist results, task statuses, and execution status."""

        if self.execution_service_context is None:
            raise RuntimeError(
                "Execution persistence is not configured."
            )

        statuses = scheduler.export_statuses()

        execution_status, waiting_task_id = (
            self._get_execution_status(statuses)
        )

        serialized_results = self._serialize_results(results)

        logger.info(
            "planner.execution_state_persistence_started "
            "execution_id=%s execution_status=%s waiting_task_id=%s "
            "task_statuses=%s",
            execution_id,
            execution_status,
            waiting_task_id,
            statuses,
        )

        async with self.execution_service_context() as service:
            await service.update_execution(
                execution_id=execution_id,
                results=serialized_results,
                task_statuses=statuses,
                status=execution_status,
                waiting_task_id=waiting_task_id,
            )

        logger.info(
            "planner.execution_state_persisted "
            "execution_id=%s execution_status=%s waiting_task_id=%s",
            execution_id,
            execution_status,
            waiting_task_id,
        )

    # ============================================================
    # GOVERNANCE
    # ============================================================

    async def _check_governance(
        self,
        task: Task,
        arguments: dict[str, Any],
        user_id: int | None,
        execution_id: int,
    ) -> dict[str, Any] | None:

        if (
            self.governance_engine is None
            or self.governance_context_builder is None
        ):
            if task.operation == "place_order":
                return {
                    "ok": False,
                    "error": {
                        "code": "GOVERNANCE_UNAVAILABLE",
                        "message": "Governance is not configured.",
                    },
                }

            return None

        context = PolicyContext(
            task_id=task.id,
            operation=task.operation,
            user_id=user_id,
            arguments=arguments,
        )

        # Trusted facts are loaded by the backend context builder.
        # Planner arguments must never be treated as checkout authority.
        context = await self.governance_context_builder.build(context)

        decision = self.governance_engine.evaluate(context)

        logger.info(
            "planner.governance_evaluated "
            "task_id=%s operation=%s decision=%s "
            "reason_codes=%s matched_policy_ids=%s",
            task.id,
            task.operation,
            decision.decision.value,
            decision.reason_codes,
            decision.matched_policy_ids,
        )

        governance_data = decision.model_dump(mode="json")

        # --------------------------------------------------------
        # ALLOW
        # --------------------------------------------------------

        if decision.decision == GovernanceDecision.ALLOW:
            return None

        # --------------------------------------------------------
        # DENY
        # --------------------------------------------------------

        if decision.decision == GovernanceDecision.DENY:
            reason_code = (
                decision.reason_codes[0]
                if decision.reason_codes
                else "GOVERNANCE_DENIED"
            )

            return {
                "ok": False,
                "error": {
                    "code": reason_code,
                    "message": "This operation is not permitted.",
                },
                "governance": governance_data,
            }

        # --------------------------------------------------------
        # REQUIRE_APPROVAL
        # --------------------------------------------------------

        if decision.decision == GovernanceDecision.REQUIRE_APPROVAL:

            if self.approval_service_context is None:
                logger.error(
                    "planner.approval_service_unavailable "
                    "task_id=%s operation=%s",
                    task.id,
                    task.operation,
                )

                return {
                    "ok": False,
                    "error": {
                        "code": "APPROVAL_SERVICE_UNAVAILABLE",
                        "message": "Approval service is not configured.",
                    },
                    "governance": governance_data,
                }

            if user_id is None:
                return {
                    "ok": False,
                    "error": {
                        "code": "APPROVAL_USER_UNAVAILABLE",
                        "message": (
                            "Cannot create approval without "
                            "an authenticated user."
                        ),
                    },
                    "governance": governance_data,
                }

            approval_policy = next(
                (
                    result
                    for result in decision.policy_results
                    if result.decision
                    == GovernanceDecision.REQUIRE_APPROVAL
                ),
                None,
            )

            if approval_policy is None:
                logger.error(
                    "planner.approval_policy_result_missing task_id=%s",
                    task.id,
                )

                return {
                    "ok": False,
                    "error": {
                        "code": "APPROVAL_POLICY_RESULT_MISSING",
                        "message": (
                            "Unable to identify the policy "
                            "requiring approval."
                        ),
                    },
                    "governance": governance_data,
                }

            required_fact_keys = (
                "cart_id",
                "order_total",
                "currency",
                "cart_snapshot",
            )

            missing_facts = [
                key
                for key in required_fact_keys
                if key not in context.attributes
                or context.attributes[key] is None
            ]

            if missing_facts:
                logger.error(
                    "planner.approval_checkout_facts_incomplete "
                    "task_id=%s missing_facts=%s",
                    task.id,
                    missing_facts,
                )

                return {
                    "ok": False,
                    "error": {
                        "code": "APPROVAL_FACTS_UNAVAILABLE",
                        "message": (
                            "Trusted checkout information is incomplete."
                        ),
                    },
                    "governance": governance_data,
                }

            checkout_facts = {
                key: context.attributes[key]
                for key in required_fact_keys
            }

            logger.info(
                "planner.approval_request_creation_started "
                "task_id=%s user_id=%s execution_id=%s "
                "policy_id=%s reason_code=%s",
                task.id,
                user_id,
                execution_id,
                approval_policy.policy_id,
                approval_policy.reason_code,
            )

            async with self.approval_service_context() as approval_service:
                approval = await approval_service.create_request(
                    user_id=user_id,
                    execution_id=execution_id,
                    checkout_facts=checkout_facts,
                    policy_id=approval_policy.policy_id,
                    reason_code=approval_policy.reason_code,
                )

            logger.info(
                "planner.approval_request_created "
                "task_id=%s approval_id=%s execution_id=%s status=%s",
                task.id,
                approval.id,
                execution_id,
                approval.status,
            )

            return {
                "ok": False,
                "approval_required": True,
                "approval_id": approval.id,
                "approval_status": approval.status,
                "execution_id": execution_id,
                "execution_status": "WAITING_FOR_APPROVAL",
                "message": (
                    approval_policy.message
                    or "This operation requires approval before execution."
                ),
                "governance": governance_data,
            }

        return {
            "ok": False,
            "error": {
                "code": "UNKNOWN_GOVERNANCE_DECISION",
                "message": (
                    "Governance returned an unsupported decision."
                ),
            },
            "governance": governance_data,
        }

    # ============================================================
    # ARGUMENT RESOLUTION
    # ============================================================

    def _resolve_arguments(
        self,
        task: Task,
        completed_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve runtime references and merge them with literal arguments."""

        resolved = dict(task.arguments)

        for argument_name, reference in task.input_refs.items():
            value = resolve_input_reference(
                reference=reference,
                completed_results=completed_results,
            )

            resolved[argument_name] = value

            logger.info(
                "planner.reference_resolved task_id=%s argument=%s "
                "source_task_id=%s source_path=%s",
                task.id,
                argument_name,
                reference.task_id,
                reference.path,
            )

        return resolved

    @staticmethod
    def _result_indicates_failure(result: Any) -> bool:
        """Recognize structured tool failures, including JSON strings."""

        if isinstance(result, dict):
            return result.get("ok") is False

        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return False

            return (
                isinstance(parsed, dict)
                and parsed.get("ok") is False
            )

        return False

    # ============================================================
    # SINGLE TASK EXECUTION
    # ============================================================

    async def _execute_one(
        self,
        task: Task,
        completed_results: dict[str, Any],
        user_id: int | None,
        execution_id: int,
    ) -> tuple[str, Any, bool]:
        """
        Execute one task.

        Returns:
            (task_id, result, failed)

        Scheduler statuses and shared results are updated by
        _execute_batch(), not by this method.
        """

        logger.info(
            "planner.task_started task_id=%s operation=%s "
            "execution_id=%s",
            task.id,
            task.operation,
            execution_id,
        )

        try:
            spec = self.registry[task.operation]

            arguments = self._resolve_arguments(
                task=task,
                completed_results=completed_results,
            )

            logger.debug(
                "planner.task_resolved_arguments "
                "task_id=%s arguments=%s",
                task.id,
                pformat(arguments, sort_dicts=False),
            )

            validated = spec.arguments_schema.model_validate(arguments)
            validated_arguments = validated.model_dump(mode="python")

            logger.debug(
                "planner.task_validated_arguments "
                "task_id=%s arguments=%s",
                task.id,
                pformat(validated_arguments, sort_dicts=False),
            )

            governance_result = await self._check_governance(
                task=task,
                arguments=validated_arguments,
                user_id=user_id,
                execution_id=execution_id,
            )

            if governance_result is not None:
                logger.warning(
                    "planner.task_blocked_by_governance "
                    "task_id=%s result=%s",
                    task.id,
                    pformat(governance_result),
                )

                # A waiting approval is not a failed operation.
                is_waiting = (
                    governance_result.get("execution_status")
                    == "WAITING_FOR_APPROVAL"
                )

                return task.id, governance_result, not is_waiting

            result = await spec.execute.ainvoke(validated_arguments)

            failed = self._result_indicates_failure(result)

            logger.info(
                "planner.task_output task_id=%s operation=%s "
                "output_type=%s failed=%s output=%s",
                task.id,
                task.operation,
                type(result).__name__,
                failed,
                pformat(result, sort_dicts=False),
            )

            return task.id, result, failed

        except Exception as exc:
            logger.exception(
                "planner.task_execution_exception "
                "task_id=%s operation=%s execution_id=%s",
                task.id,
                task.operation,
                execution_id,
            )

            return (
                task.id,
                {
                    "ok": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                True,
            )

    # ============================================================
    # BATCH EXECUTION
    # ============================================================

    async def _execute_batch(
        self,
        batch: list[Task],
        completed_results: dict[str, Any],
        scheduler: DependencyAwareScheduler,
        batch_number: int,
        user_id: int | None,
        execution_id: int,
    ) -> None:
        """Execute a selected batch concurrently and update statuses."""

        logger.info(
            "planner.executor_parallel_batch_started "
            "batch_number=%d task_ids=%s batch_size=%d "
            "execution_id=%s",
            batch_number,
            [task.id for task in batch],
            len(batch),
            execution_id,
        )

        outcomes = await asyncio.gather(
            *[
                self._execute_one(
                    task=task,
                    completed_results=completed_results,
                    user_id=user_id,
                    execution_id=execution_id,
                )
                for task in batch
            ]
        )

        for task_id, result, failed in outcomes:
            completed_results[task_id] = result

            if (
                isinstance(result, dict)
                and result.get("execution_status")
                == "WAITING_FOR_APPROVAL"
            ):
                scheduler.mark_waiting_for_approval(task_id)

                logger.info(
                    "planner.executor_task_waiting_for_approval "
                    "task_id=%s approval_id=%s execution_id=%s",
                    task_id,
                    result.get("approval_id"),
                    execution_id,
                )

            elif failed:
                scheduler.mark_failed(task_id)

                logger.warning(
                    "planner.executor_reported_failure "
                    "task_id=%s operation=%s",
                    task_id,
                    scheduler.tasks[task_id].operation,
                )

            else:
                scheduler.mark_succeeded(task_id)

                logger.info(
                    "planner.executor_reported_success "
                    "task_id=%s operation=%s",
                    task_id,
                    scheduler.tasks[task_id].operation,
                )

        logger.info(
            "planner.executor_parallel_batch_finished "
            "batch_number=%d task_ids=%s statuses=%s",
            batch_number,
            [task.id for task in batch],
            scheduler.statuses,
        )

    # ============================================================
    # MAIN EXECUTION LOOP
    # ============================================================

    async def execute(
        self,
        plan: Plan,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Execute the plan and persist its progress.

        The execution record is created before any operation runs.
        Task statuses are persisted before and after each batch.
        """

        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or user_id <= 0
        ):
            raise ValueError("A valid authenticated user_id is required.")

        logger.info(
            "planner.execution_started user_id=%s task_count=%d",
            user_id,
            len(plan.tasks),
        )

        scheduler = DependencyAwareScheduler(
            plan=plan,
            registry=self.registry,
            max_batch_size=self.max_batch_size,
        )

        results: dict[str, Any] = {}
        batch_number = 0

        execution_id = await self._create_execution_record(
            plan=plan,
            user_id=user_id,
            scheduler=scheduler,
        )

        logger.info(
            "planner.executor_scheduler_created execution_id=%s "
            "task_ids=%s initial_statuses=%s prerequisites=%s",
            execution_id,
            list(scheduler.tasks.keys()),
            scheduler.statuses,
            scheduler.prerequisites,
        )

        while True:
            logger.info(
                "planner.scheduler_requesting_next_batch "
                "execution_id=%s completed_task_ids=%s "
                "current_statuses=%s",
                execution_id,
                list(results.keys()),
                scheduler.statuses,
            )

            batch = scheduler.next_batch()

            if not batch:
                logger.info(
                    "planner.scheduler_finished execution_id=%s "
                    "no_more_tasks=true final_statuses=%s",
                    execution_id,
                    scheduler.statuses,
                )
                break

            batch_number += 1

            logger.info(
                "planner.executor_batch_received "
                "execution_id=%s batch_number=%d task_ids=%s",
                execution_id,
                batch_number,
                [task.id for task in batch],
            )

            # IMPORTANT:
            # next_batch() has marked these tasks as "running".
            # Persist that state BEFORE invoking any tools.
            await self._persist_execution_state(
                execution_id=execution_id,
                results=results,
                scheduler=scheduler,
            )

            await self._execute_batch(
                batch=batch,
                completed_results=results,
                scheduler=scheduler,
                batch_number=batch_number,
                user_id=user_id,
                execution_id=execution_id,
            )

            # Persist completed results and the updated statuses.
            await self._persist_execution_state(
                execution_id=execution_id,
                results=results,
                scheduler=scheduler,
            )

        # Record skipped tasks in the results dictionary.
        for task_id, status in scheduler.statuses.items():
            if status == "skipped":
                results[task_id] = {
                    "ok": False,
                    "skipped": True,
                    "error": "A prerequisite task did not succeed.",
                }

                logger.warning(
                    "planner.executor_recorded_skipped_task "
                    "task_id=%s",
                    task_id,
                )

        # Persist the final execution state as well.
        await self._persist_execution_state(
            execution_id=execution_id,
            results=results,
            scheduler=scheduler,
        )

        execution_status, waiting_task_id = (
            self._get_execution_status(scheduler.export_statuses())
        )

        logger.info(
            "planner.execution_finished execution_id=%s "
            "execution_status=%s waiting_task_id=%s "
            "task_count=%d result_count=%d total_batches=%d "
            "final_statuses=%s",
            execution_id,
            execution_status,
            waiting_task_id,
            len(plan.tasks),
            len(results),
            batch_number,
            scheduler.statuses,
        )

        logger.debug(
            "planner.execution_final_results execution_id=%s results=%s",
            execution_id,
            pformat(results, sort_dicts=False),
        )

        return {
            "execution_id": execution_id,
            "execution_status": execution_status,
            "waiting_task_id": waiting_task_id,
            "results": results,
        }