
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


OUTPUT_DESCRIPTIONS = {
    "search_products": (
        "Describe the actual search response fields, including how "
        "to access each product's ID and name."
    ),
    "get_product": (
        "Describe the actual single-product response fields."
    ),
    "get_active_cart": (
        "Describe the actual cart response and its item fields."
    ),
    "add_item": (
        "Describe the actual successful cart-mutation response."
    ),
    "remove_item": (
        "Returns a result indicating whether the cart item was removed "
        "successfully, potentially including a message or error."
    ),
    "list_orders": (
        "Describe the actual order-list response and order IDs."
    ),
    "get_order": (
        "Describe the actual single-order response."
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

missing_descriptions = set(OPERATION_ACCESS) - set(OUTPUT_DESCRIPTIONS)
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
        output_description=OUTPUT_DESCRIPTIONS[name],
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

    logger.info("planner.node_started")

    proposed_plan = await planner.create_plan(user_request)
    validated_plan = validate_plan(proposed_plan, registry)

    for task in validated_plan.tasks:
        logger.info(
            "planner.validated_task task_id=%s operation=%s "
            "depends_on=%s input_refs=%s",
            task.id,
            task.operation,
            task.depends_on,
            list(task.input_refs),
        )

    logger.info(
        "planner.node_completed task_count=%d",
        len(validated_plan.tasks),
    )

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

    if not isinstance(user_request, str):
        raise ValueError("Expected a text user request.")

    execution_results = state["results"]

    # Log the authoritative outputs from the executor.
    logger.info(
        "final_response.execution_results=%s",
        execution_results,
    )

    messages = [
        SystemMessage(content=(
            "You are an ecommerce customer support assistant. "
            "Answer the user's request using the execution results "
            "provided below. Do not invent data. "
            "Use get_active_cart as the authoritative source for "
            "the final current cart state. Do not append items from "
            "add_item to the cart returned by get_active_cart, "
            "because add_item has already changed that cart. "
            "Use list_orders as the source for order information. "
            "If any operation failed, explain that failure."
        )),
        HumanMessage(content=(
            f"User request:\n{user_request}\n\n"
            f"Execution results:\n{execution_results}"
        )),
    ]

    # Log the exact messages supplied to the model.
    logger.info(
        "final_response.model_input=%s",
        [
            {"role": message.type, "content": message.content}
            for message in messages
        ],
    )

    response = await model.ainvoke(messages)

    # Log the final model output.
    logger.info(
        "final_response.model_output=%s",
        response.content,
    )

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
