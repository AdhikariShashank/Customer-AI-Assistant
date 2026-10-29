import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.dependencies import (
    executor,
    model,
    planner,
    registry,
)
from app.agent.state import PlannerAgentState
from app.planner.validator import validate_plan
from langchain_core.runnables import RunnableConfig


logger = logging.getLogger(__name__)


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



async def execution_node(
    state: PlannerAgentState,
    config: RunnableConfig,
):
    configurable = config.get("configurable", {})
    user_id = configurable.get("user_id")

    # Fail closed if authenticated identity is missing or invalid.
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id < 1
    ):
        raise ValueError(
            "A valid authenticated user_id is required for execution."
        )

    logger.info(
        "planner.execution_node_started user_id=%s",
        user_id,
    )

    results = await executor.execute(
        state["plan"],
        user_id=user_id,
    )

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

    logger.info(
        "final_response.execution_results=%s",
        execution_results,
    )

    messages = [
        SystemMessage(
            content=(
                "You are an ecommerce customer support assistant. "
                "Answer the user's request using the execution results "
                "provided below. Do not invent data. "
                "Use get_active_cart as the authoritative source for "
                "the final current cart state. Do not append items from "
                "add_item to the cart returned by get_active_cart, "
                "because add_item has already changed that cart. "
                "Use list_orders as the source for order information. "
                "If any operation failed, explain that failure."
            )
        ),
        HumanMessage(
            content=(
                f"User request:\n{user_request}\n\n"
                f"Execution results:\n{execution_results}"
            )
        ),
    ]

    logger.info(
        "final_response.model_input=%s",
        [
            {"role": message.type, "content": message.content}
            for message in messages
        ],
    )

    response = await model.ainvoke(messages)

    logger.info(
        "final_response.model_output=%s",
        response.content,
    )

    return {"messages": [response]}
