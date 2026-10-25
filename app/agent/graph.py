from langgraph.graph import StateGraph, START, END

from app.agent.state import PlannerAgentState
from app.agent.nodes import (
    planning_node,
    execution_node,
    response_node,
)


def build_graph():
    builder = StateGraph(PlannerAgentState)

    builder.add_node("plan", planning_node)
    builder.add_node("execute", execution_node)
    builder.add_node("respond", response_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "respond")
    builder.add_edge("respond", END)

    return builder.compile()


graph = build_graph()
