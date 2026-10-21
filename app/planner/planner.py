
import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.planner.prompts import SYSTEM_PROMPT
from app.planner.schemas import Plan
from app.planner.operations import OperationSpec


class Planner:
    def __init__(
        self,
        model: ChatOpenAI,
        registry: dict[str, OperationSpec],
    ):
        self.registry = registry

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
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
        
# The important distinction
# You have two different schemas working together:
# - Operation catalog schema: Describes what each operation accepts, such as search_products(query, limit) or add_to_cart(product_id, quantity).
# - Plan schema: Describes the structure of the plan itself, such as its list of tasks, operation names, arguments, and dependencies (depending on how you've defined your model).     

    def _build_operation_catalog(self) -> str:
        catalog = []

        for name, spec in self.registry.items():
            catalog.append(
                {
                    "operation": name,
                    "access": spec.access,
                    "arguments_schema": spec.arguments_schema.model_json_schema(),
                }
            )

        return json.dumps(catalog, indent=2)

    async def create_plan(self, user_request: str) -> Plan:
        if not user_request or not user_request.strip():
            raise ValueError("User request cannot be empty.")

        return await self.chain.ainvoke(
            {
                "user_request": user_request.strip(),
                "operation_catalog": self._build_operation_catalog(),
            }
        )
