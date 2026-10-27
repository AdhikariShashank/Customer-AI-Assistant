import json
import logging

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.planner.prompts import SYSTEM_PROMPT
from app.planner.schemas import Plan
from app.planner.operations import OperationSpec

logger = logging.getLogger(__name__)


class Planner:
    def __init__(
        self,
        model: ChatOpenAI,
        registry: dict[str, OperationSpec],
    ):
        self.registry = registry

        self.prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                (
                    "human",
                    "User request:\n{user_request}\n\n"
                    "Available operations and argument schemas:\n"
                    "{operation_catalog}\n\n"
                    "Validation feedback from the previous attempt:\n"
                    "{validation_feedback}\n\n"
                    "If this is a retry, correct the reported errors and "
                    "return the entire corrected Plan. Do not return "
                    "a partial plan.",
                ),
            ]
        )

        self.structured_model = model.with_structured_output(
            Plan,
            method="function_calling",
            include_raw=True,
        )

        self.chain = self.prompt | self.structured_model

    def _build_operation_catalog(self) -> str:
        catalog = []

        for name, spec in self.registry.items():
            catalog.append(
                {
                    "operation": name,
                    "access": spec.access,
                    "arguments_schema": (
                        spec.arguments_schema.model_json_schema()
                    ),
                    "output_description": spec.output_description,
                }
            )

        return json.dumps(catalog, indent=2)

    
    
    async def create_plan(self, user_request: str) -> Plan:
        if not user_request or not user_request.strip():
            raise ValueError("User request cannot be empty.")

        max_attempts = 3
        validation_feedback = "No previous attempt. Generate the plan."

        logger.info(
            "planner.plan_generation_started request_length=%d",
            len(user_request),
        )

        try:
            for attempt in range(1, max_attempts + 1):
                logger.info(
                    "planner.generation_attempt attempt=%d max_attempts=%d",
                    attempt,
                    max_attempts,
                )

                response = await self.chain.ainvoke(
                    {
                        "user_request": user_request.strip(),
                        "operation_catalog": self._build_operation_catalog(),
                        "validation_feedback": validation_feedback,
                    }
                )

                raw_message = response["raw"]

                # Keep raw tool-call details out of normal production logs.
                logger.debug(
                    "planner.raw_tool_calls=%r",
                    raw_message.tool_calls,
                )

                parsing_error = response["parsing_error"]

                if parsing_error is not None:
                    logger.warning(
                        "planner.parsing_failed attempt=%d error=%s",
                        attempt,
                        parsing_error,
                    )

                    validation_feedback = (
                        f"Attempt {attempt} failed validation.\n"
                        f"Errors:\n{parsing_error}\n\n"
                        "Regenerate the entire Plan. Every item in tasks "
                        "must be a complete Task object. Include every "
                        "required field. If input_refs references a task, "
                        "include that task ID in depends_on. Ensure all "
                        "dependencies refer to existing tasks and appear "
                        "before their dependent tasks."
                    )
                    continue

                plan = response["parsed"]

                if not isinstance(plan, Plan):
                    logger.warning(
                        "planner.missing_plan attempt=%d",
                        attempt,
                    )

                    validation_feedback = (
                        "The previous attempt did not produce a valid Plan. "
                        "Return the entire Plan using the required schema."
                    )
                    continue

                logger.info(
                    "planner.plan_generation_succeeded "
                    "attempt=%d goal=%r task_count=%d",
                    attempt,
                    plan.goal,
                    len(plan.tasks),
                )

                for task in plan.tasks:
                    logger.info(
                        "planner.proposed_task task_id=%s operation=%s "
                        "dependencies=%s input_ref_names=%s",
                        task.id,
                        task.operation,
                        task.depends_on,
                        list(task.input_refs.keys()),
                    )

                return plan

            raise ValueError(
                f"Planner failed to produce a valid plan after "
                f"{max_attempts} attempts."
            )

        except Exception:
            logger.exception("planner.plan_generation_failed")
            raise
