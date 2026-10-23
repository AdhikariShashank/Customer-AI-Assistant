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
                    "{operation_catalog}",
                ),
            ]
        )

        self.structured_model = model.with_structured_output(
            Plan,
            method="function_calling",
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

        logger.info(
            "planner.plan_generation_started request_length=%d",
            len(user_request),
        )

        try:
            plan = await self.chain.ainvoke(
                {
                    "user_request": user_request.strip(),
                    "operation_catalog": self._build_operation_catalog(),
                }
            )

            logger.info(
                "planner.plan_generation_succeeded goal=%r task_count=%d",
                plan.goal,
                len(plan.tasks),
            )

            for task in plan.tasks:
                logger.info(
                    "planner.proposed_task task_id=%s operation=%s "
                    "dependencies=%s input_refs=%s",
                    task.id,
                    task.operation,
                    task.depends_on,
                    {
                        name: {
                            "task_id": ref.task_id,
                            "path": ref.path,
                        }
                        for name, ref in task.input_refs.items()
                    },
                )

            return plan

        except Exception:
            logger.exception("planner.plan_generation_failed")
            raise