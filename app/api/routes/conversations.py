from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.conversations import CreateConversationBody, PostConversationMessageBody
from app.services.conversations import create_conversation, get_conversation, list_conversations, post_conversation_message

router = APIRouter(prefix="/v1/conversations", tags=["conversations"], dependencies=[Depends(require_internal_api_key)])


@router.post("")
async def post_conversation(body: CreateConversationBody) -> dict:
    return {"success": True, "data": await create_conversation(body)}


@router.get("")
async def get_conversations() -> dict:
    return {"success": True, "data": await list_conversations()}


@router.get("/{conversation_id}")
async def get_conversation_by_id(conversation_id: str) -> dict:
    return {"success": True, "data": await get_conversation(conversation_id)}


@router.post("/{conversation_id}/messages")
async def post_message_to_conversation(
    conversation_id: str,
    body: PostConversationMessageBody,
) -> dict:
    return {"success": True, "data": await post_conversation_message(conversation_id, body.content, body.parts)}
