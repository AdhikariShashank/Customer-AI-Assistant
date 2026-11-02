from typing import Any

from langgraph.graph import MessagesState

from app.planner.schemas import Plan


class PlannerAgentState(MessagesState):
    plan: Plan

    execution_id: int | None
    execution_status: str | None

    results: dict[str, Any]