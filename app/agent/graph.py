
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
    "search_products": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - filters: object containing query, category, min_price, max_price.
    - products: list of product objects, each containing:
        - id: product ID.
        - name: product name.
        - category: product category.
        - description: product description.
        - price: product price.
        - stock: available stock.
    - pagination: object containing limit, offset, total, returned,
      and has_more.
    Use products.0.id to reference the first product's ID.
    Use products.0.name to reference the first product's name.
    For selecting a product by a field rather than position, use
    path="products" with select_by and select_field.
    """,

    "get_product": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - product: object containing:
        - id: product ID.
        - name: product name.
        - category: product category.
        - description: product description.
        - price: product price.
        - stock: available stock.
    Use product.id to reference the product ID.
    Use product.name to reference the product name.
    """,

    "get_active_cart": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - cart: object containing:
        - id: cart ID.
        - status: cart status.
        - items: list of cart item objects, each containing:
            - item_id: cart item ID used by remove_item.
            - product_id: ID of the product in the cart.
            - name: product name.
            - quantity: item quantity.
            - unit_price: unit price.
            - subtotal: item subtotal.
        - item_count: total quantity across all cart items.
        - total: cart total.
    Use cart.items, not cart.products.
    Each cart item uses product_id for the product ID and item_id
    for the cart item's own ID. These IDs are not interchangeable.
    To remove a product by product ID, select the matching item from
    cart.items using select_by={"field": "product_id", "value": <ID>}
    and extract item_id using select_field="item_id".
    Do not assume the cart item is at a fixed list position.
    """,

    "add_item": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - message: operation result message.
    - cart: updated cart object containing:
        - id: cart ID.
        - status: cart status.
        - items: list of cart item objects, each containing:
            - item_id: cart item ID.
            - product_id: product ID.
            - name: product name.
            - quantity: updated item quantity.
            - unit_price: unit price.
            - subtotal: updated item subtotal.
        - item_count: total quantity across all cart items.
        - total: updated cart total.
    Use cart.items to inspect the updated cart.
    """,

    "remove_item": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - message: operation result message, when available.
    - error: error details when the operation fails, when available.
    - cart: updated cart object on a successful removal, containing:
        - id: cart ID.
        - status: cart status.
        - items: remaining cart item objects, each containing:
            - item_id: cart item ID.
            - product_id: product ID.
            - name: product name.
            - quantity: item quantity.
            - unit_price: unit price.
            - subtotal: item subtotal.
        - item_count: total quantity across remaining cart items.
        - total: updated cart total.
    The tool's item_id argument requires a cart item ID, not a product ID.
    If the user identifies a product by product ID, first retrieve the
    active cart and resolve the matching cart item's item_id.
    Check ok before treating the operation as successful.
    """,

    "list_orders": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - orders: list of order objects, each containing:
        - id: order ID.
        - user_id: owner user ID.
        - status: order status.
        - total_amount: order total.
        - created_at: order creation timestamp.
        - items: list of order item objects, each containing:
            - order_item_id: order line-item ID.
            - product_id: product ID.
            - product_name: product name.
            - quantity: ordered quantity.
            - unit_price: unit price.
            - subtotal: line-item subtotal.
    - count: number of orders returned.
    - total_count: total number of matching orders.
    Use orders.0.id to reference the first returned order's ID.
    Do not assume that the first order is the order the user means
    unless the request or result establishes that.
    """,

    "get_order": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - order: object containing:
        - id: order ID.
        - user_id: owner user ID.
        - status: order status.
        - total_amount: order total.
        - created_at: order creation timestamp.
        - items: list of order item objects, each containing:
            - order_item_id: order line-item ID.
            - product_id: product ID.
            - product_name: product name.
            - quantity: ordered quantity.
            - unit_price: unit price.
            - subtotal: line-item subtotal.
    Use order.id to reference the order ID.
    """,

    "place_order": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - message: operation result message, when available.
    - order: created order object on success, containing:
        - id: new order ID.
        - user_id: owner user ID.
        - status: order status.
        - total_amount: order total.
        - created_at: order creation timestamp.
        - items: list of order item objects, each containing:
            - order_item_id: order line-item ID.
            - product_id: product ID.
            - product_name: product name.
            - quantity: ordered quantity.
            - unit_price: unit price.
            - subtotal: line-item subtotal.
    Check ok before treating the operation as successful.
    Use order.id to reference the newly created order ID.
    """,
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
