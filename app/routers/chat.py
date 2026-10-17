from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from app.agent.graph import graph
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

class ChatResponse(BaseModel):
    response: str



@router.post("/", response_model=SuccessResponse[ChatResponse])
async def chat(request: ChatRequest):
    try:
        result = await graph.ainvoke({
            "messages": [
                {
                    "role": "user",
                    "content": request.message,
                }
            ]
        })

        messages = result["messages"]

        final_message = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, AIMessage)
                and not message.tool_calls
            ),
            None,
        )

        if final_message is None:
            raise HTTPException(
                status_code=500,
                detail="The agent did not generate a final response.",
            )

        return SuccessResponse(
            data={
                "response": final_message.content,
            },
            message="Chat response generated successfully",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to process your message.",
        ) from exc