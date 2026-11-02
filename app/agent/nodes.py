
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


# Operations that can establish approval status.
APPROVAL_OPERATIONS = {
    "get_pending_approval",
    "get_pending_approvals",
    "get_user_approvals",
}


def was_approval_checked(results: dict) -> bool:
    """
    Return True only when an approval-related operation
    successfully returned approval information.
    """

    for operation_name in APPROVAL_OPERATIONS:
        operation_result = results.get(operation_name)

        if not isinstance(operation_result, dict):
            continue

        if operation_result.get("ok") is not True:
            continue

        if "has_pending_approval" in operation_result:
            return True

        if "approvals" in operation_result:
            return True

        if "approval" in operation_result:
            return True

    return False


def get_approval_verification_message(results: dict) -> str:
    """
    Produce a deterministic approval verification instruction.
    """

    if was_approval_checked(results):
        return (
            "Approval status was successfully checked. "
            "Use the returned approval information as the "
            "authoritative source."
        )

    return (
        "Approval status was NOT verified. No successful "
        "approval lookup operation returned approval information. "
        "You MUST NOT claim that a pending approval exists or "
        "that no pending approval exists. Explicitly tell the user "
        "that approval status could not be verified because "
        "no approval lookup operation was executed successfully."
    )


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

    if not isinstance(execution_results, dict):
        execution_results = {}

    approval_status_verified = was_approval_checked(
        execution_results
    )

    approval_verification_message = (
        get_approval_verification_message(execution_results)
    )

    logger.info(
        "final_response.started execution_id=%s status=%s",
        execution_id,
        execution_status,
    )

    logger.info(
        "final_response.approval_verification "
        "verified=%s",
        approval_status_verified,
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

                "Approval information rules: "
                "The Approval status verified field is authoritative. "
                "If it is false, you MUST NOT claim that an approval "
                "exists or that no approval exists. Instead, explicitly "
                "state that approval status could not be verified. "
                "If it is true, use only the approval information "
                "returned by the approval operation. "
                "Cart information alone cannot establish whether "
                "an approval exists. "
                "Never infer that no pending approval exists from "
                "an empty or missing approval result. "
                "If has_pending_approval is true, report the approval "
                "details returned by the operation. "
                "If has_pending_approval is false, report that there "
                "is no pending approval. "
                "Do not confuse an approval belonging to an earlier "
                "execution with a new execution. "

                "Currency formatting rules: "
                "Use the currency returned by the execution results "
                "when displaying monetary amounts. "
                "For INR, use the ₹ symbol, never $. "
                "Do not assume a currency if it is not provided. "

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
                f"Approval status verified:\n"
                f"{approval_status_verified}\n\n"
                f"Approval verification instruction:\n"
                f"{approval_verification_message}\n\n"
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
