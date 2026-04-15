from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.agent import AgentChatBody
from app.services.agent import chat_with_agent

router = APIRouter(prefix="/v1/agent", tags=["agent"], dependencies=[Depends(require_internal_api_key)])


@router.post("/chat")
async def post_agent_chat(body: AgentChatBody) -> dict:
    return {"success": True, "data": await chat_with_agent(body)}
