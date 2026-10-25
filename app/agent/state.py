from typing import Any

from langgraph.graph import MessagesState

from app.planner.schemas import Plan


class PlannerAgentState(MessagesState):
    plan: Plan
    results: dict[str, Any]