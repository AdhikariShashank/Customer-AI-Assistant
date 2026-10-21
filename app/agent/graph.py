
import logging
from typing import Any
from typing_extensions import TypedDict


from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END

from app.tools.cart import create_cart_tools
from app.tools.order import create_order_tools
from app.tools.product import create_product_tools
from app.tools.dependencies import (
    cart_service_context,
    order_service_context,
    product_service_context,
)

from app.planner.planner import Planner
from app.planner.operations import OperationSpec
from app.planner.validator import validate_plan
from app.planner.executor import SequentialExecutor
from app.planner.schemas import Plan


logger = logging.getLogger(__name__)


# --------------------------------------------------
# 1. Create your existing tools
# --------------------------------------------------

tools = [
    *create_product_tools(product_service_context),
    *create_cart_tools(cart_service_context),
    *create_order_tools(order_service_context),
]

tools_by_name = {tool.name: tool for tool in tools}


# --------------------------------------------------
# 2. Build the operation registry
# --------------------------------------------------

# IMPORTANT:
# These names must match your actual tool names.
# Replace the names below if your tools use different names.


tools = [
    *create_product_tools(product_service_context),
    *create_cart_tools(cart_service_context),
    *create_order_tools(order_service_context),
]

tools_by_name = {tool.name: tool for tool in tools}


output_descriptions = {
    "search_products": (
        "Returns a dictionary containing a products list. "
        "Each product contains id, name, and price. "
        "Example product ID path: products[0].id."
    ),
    "get_product": (
        "Returns one product containing id, name, and price."
    ),
    "get_active_cart": (
        "Returns the user's active cart and its items."
    ),
    "add_item": (
        "Returns the updated cart and its items."
    ),
    "remove_item": (
        "Returns the updated cart and its items."
    ),
    "list_orders": (
        "Returns a list of the user's orders."
    ),
    "get_order": (
        "Returns one order and its details."
    ),
    "place_order": (
        "Returns the placed order and its details."
    ),
}

OPERATION_ACCESS = {
    "search_products": "read",
    "get_product": "read",
    "get_active_cart": "read",
    "add_item": "write",
    "remove_item": "write",
    "list_orders": "read",
    "get_order": "read",
    "place_order": "write",
}

missing = set(OPERATION_ACCESS) - set(tools_by_name)
if missing:
    raise RuntimeError(
        f"Planner operations missing from tool list: {sorted(missing)}"
    )

missing_descriptions = set(OPERATION_ACCESS) - set(output_descriptions)
if missing_descriptions:
    raise RuntimeError(
        f"Missing output descriptions: {sorted(missing_descriptions)}"
    )

registry = {
    name: OperationSpec(
        name=name,
        arguments_schema=tools_by_name[name].args_schema,
        execute=tools_by_name[name],
        access=access,
        output_description=output_descriptions[name],
    )
    for name, access in OPERATION_ACCESS.items()
}



# --------------------------------------------------
# 3. Initialize the planner and executor
# --------------------------------------------------

model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

planner = Planner(
    model=model,
    registry=registry,
)

executor = SequentialExecutor(registry)


# --------------------------------------------------
# 4. Define graph state
# --------------------------------------------------

class PlannerAgentState(MessagesState):
    plan: Plan
    results: dict[str, Any]


# --------------------------------------------------
# 5. Define the planning node
# --------------------------------------------------

async def planning_node(state: PlannerAgentState):
    # Find the latest user message.
    user_messages = [
        message
        for message in state["messages"]
        if isinstance(message, HumanMessage)
    ]

    if not user_messages:
        raise ValueError("No user message found.")

    user_request = user_messages[-1].content

    if not isinstance(user_request, str):
        raise ValueError("Expected a text user request.")

    # Explicit call 1: invoke the LLM and parse its output as Plan.
    proposed_plan = await planner.create_plan(user_request)

    logger.info(
    "Planner proposed plan: %s",
    proposed_plan.model_dump(),
    )

    # Explicit call 2: validate arguments against registered tool schemas.
    validated_plan = validate_plan(proposed_plan, registry)

    return {"plan": validated_plan}


# --------------------------------------------------
# 6. Define the execution node
# --------------------------------------------------

async def execution_node(state: PlannerAgentState):
    # Explicit call 3: execute the validated tasks.
    results = await executor.execute(state["plan"])

    return {"results": results}


async def response_node(state: PlannerAgentState):
    user_messages = [
        message
        for message in state["messages"]
        if isinstance(message, HumanMessage)
    ]

    if not user_messages:
        raise ValueError("No user message found.")

    user_request = user_messages[-1].content

    response = await model.ainvoke([
        SystemMessage(content=(
            "You are an ecommerce customer support assistant. "
            "Answer the user's request using the execution results "
            "provided below. Do not invent data. If the results "
            "contain an error, explain that the operation failed."
        )),
        HumanMessage(content=(
            f"User request:\n{user_request}\n\n"
            f"Execution results:\n{state['results']}"
        )),
    ])

    return {"messages": [response]}

# --------------------------------------------------
# 7. Connect nodes using LangGraph
# --------------------------------------------------

builder = StateGraph(PlannerAgentState)

builder.add_node("plan", planning_node)
builder.add_node("execute", execution_node)
builder.add_node("respond", response_node)

builder.add_edge(START, "plan")
builder.add_edge("plan", "execute")
builder.add_edge("execute", "respond")
builder.add_edge("respond", END)

graph = builder.compile()
