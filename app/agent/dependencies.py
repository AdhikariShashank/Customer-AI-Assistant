
from langchain_openai import ChatOpenAI

from app.tools.cart import create_cart_tools
from app.tools.order import create_order_tools
from app.tools.product import create_product_tools
from app.tools.dependencies import (
    cart_service_context,
    order_service_context,
    product_service_context,
)

from app.planner.operations import OperationSpec
from app.planner.planner import Planner
from app.planner.executor import SequentialExecutor

from app.agent.operation_descriptions import (
    OPERATION_ACCESS,
    OUTPUT_DESCRIPTIONS,
)


# 1. Create the tools once.
tools = [
    *create_product_tools(product_service_context),
    *create_cart_tools(cart_service_context),
    *create_order_tools(order_service_context),
]

tools_by_name = {tool.name: tool for tool in tools}


# 2. Ensure every planner operation has a matching tool
#    and an output description.
missing_tools = set(OPERATION_ACCESS) - set(tools_by_name)

if missing_tools:
    raise RuntimeError(
        f"Planner operations missing from tool list: "
        f"{sorted(missing_tools)}"
    )

missing_descriptions = (
    set(OPERATION_ACCESS) - set(OUTPUT_DESCRIPTIONS)
)

if missing_descriptions:
    raise RuntimeError(
        f"Missing output descriptions: "
        f"{sorted(missing_descriptions)}"
    )


# 3. Build the operation registry.
registry = {
    name: OperationSpec(
        name=name,
        arguments_schema=tools_by_name[name].args_schema,
        execute=tools_by_name[name],
        access=access,
        output_description=OUTPUT_DESCRIPTIONS[name],
    )
    for name, access in OPERATION_ACCESS.items()
}


# 4. Initialize the model, planner, and executor.
model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)

planner = Planner(
    model=model,
    registry=registry,
)

executor = SequentialExecutor(registry)
