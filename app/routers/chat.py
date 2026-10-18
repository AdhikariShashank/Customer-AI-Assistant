import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from app.agent.graph import graph
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.security import get_current_user

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

class ChatResponse(BaseModel):
    response: str


logger = logging.getLogger(__name__)

@router.post("/", response_model=SuccessResponse[ChatResponse])
async def chat(request: ChatRequest, 
               current_user: User = Depends(get_current_user)):
    try:
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": request.message,
                    }
                ]
            },
            config={
                "configurable": {
                    "user_id": current_user.id,
                }
            },
        )

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

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Chat endpoint failed for user_id=%s",
            current_user.id,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to process your message.",
        )