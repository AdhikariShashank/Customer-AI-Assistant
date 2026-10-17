from langchain_openai import ChatOpenAI
from langgraph.graph import (
    StateGraph,
    MessagesState,
    START,
)
from langgraph.prebuilt import ToolNode, tools_condition

from app.tools.product import create_product_tools
from app.tools.dependencies import product_service_context


tools = create_product_tools(product_service_context)

model = ChatOpenAI(model="gpt-4o-mini")
model_with_tools = model.bind_tools(tools)


async def agent_node(state: MessagesState):
    response = await model_with_tools.ainvoke(
        state["messages"]
    )
    return {"messages": [response]}


tool_node = ToolNode(tools)

builder = StateGraph(MessagesState)

builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")

builder.add_conditional_edges(
    "agent",
    tools_condition,
)

builder.add_edge("tools", "agent")

graph = builder.compile()