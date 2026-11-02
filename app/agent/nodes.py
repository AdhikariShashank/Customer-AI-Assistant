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

logger = logging.getLogger(__name__)


async def planning_node(state: PlannerAgentState):
    """Generate and validate the execution plan."""

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

    return {
        "plan": validated_plan,
    }


async def execution_node(state: PlannerAgentState, config):
    """Execute the validated plan and return execution metadata."""

    user_id = config["configurable"]["user_id"]

    logger.info(
        "execution.node_started user_id=%s",
        user_id,
    )

    outcome = await executor.execute(
        plan=state["plan"],
        user_id=user_id,
    )

    execution_id = outcome["execution_id"]
    execution_status = outcome["execution_status"]
    execution_results = outcome["results"]

    logger.info(
        "execution.node_completed execution_id=%s status=%s",
        execution_id,
        execution_status,
    )

    return {
        "execution_id": execution_id,
        "execution_status": execution_status,
        "results": execution_results,
    }


async def response_node(state: PlannerAgentState):
    """Generate the final user-facing response."""

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

    execution_id = state.get("execution_id")
    execution_status = state.get("execution_status", "COMPLETED")
    execution_results = state.get("results", {})

    logger.info(
        "final_response.started execution_id=%s status=%s",
        execution_id,
        execution_status,
    )

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

                "If any operation failed, explain that failure. "

                "Execution status handling rules: "

                "If execution_status is WAITING_FOR_APPROVAL, "
                "tell the user that the requested operation is awaiting "
                "admin approval. Do not claim that the order has been "
                "placed. Do not claim that payment or checkout has "
                "completed. Explain that the operation will proceed "
                "only after approval. "

                "If execution_status is FAILED, explain that the "
                "execution could not be completed. Do not claim that "
                "the requested operation succeeded. "

                "If execution_status is RUNNING, explain that the "
                "execution is still in progress. Do not claim completion. "

                "If execution_status is COMPLETED, summarize the "
                "successfully completed operations using their results. "
                "Do not claim that an operation succeeded if its result "
                "indicates failure."
            )
        ),
        HumanMessage(
            content=(
                f"User request:\n{user_request}\n\n"
                f"Execution ID:\n{execution_id}\n\n"
                f"Execution status:\n{execution_status}\n\n"
                f"Execution results:\n{execution_results}"
            )
        ),
    ]

    logger.info(
        "final_response.model_input=%s",
        [
            {
                "role": message.type,
                "content": message.content,
            }
            for message in messages
        ],
    )

    response = await model.ainvoke(messages)

    logger.info(
        "final_response.model_output=%s",
        response.content,
    )

    return {
        "messages": [response],
    }