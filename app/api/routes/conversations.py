from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.conversations import CreateConversationBody, PostConversationMessageBody, UpdateConversationBody
from app.services.conversations import (
    cancel_conversation_message_job,
    create_conversation,
    create_conversation_message_job,
    delete_conversation,
    get_conversation,
    get_conversation_message_job,
    list_conversations,
    post_conversation_message,
    update_conversation,
)

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


@router.patch("/{conversation_id}")
async def patch_conversation_by_id(conversation_id: str, body: UpdateConversationBody) -> dict:
    return {"success": True, "data": await update_conversation(conversation_id, body)}


@router.delete("/{conversation_id}")
async def delete_conversation_by_id(conversation_id: str) -> dict:
    await delete_conversation(conversation_id)
    return {"success": True, "data": {"id": conversation_id, "deleted": True}}


@router.post("/{conversation_id}/messages")
async def post_message_to_conversation(
    conversation_id: str,
    body: PostConversationMessageBody,
) -> dict:
    return {"success": True, "data": await post_conversation_message(conversation_id, body.content, body.parts)}


@router.post("/{conversation_id}/messages/jobs", status_code=202)
async def post_message_job_to_conversation(
    conversation_id: str,
    body: PostConversationMessageBody,
) -> dict:
    return {"success": True, "data": create_conversation_message_job(conversation_id, body)}


@router.get("/{conversation_id}/messages/jobs/{job_id}")
async def get_message_job_for_conversation(conversation_id: str, job_id: str) -> dict:
    return {"success": True, "data": get_conversation_message_job(conversation_id, job_id)}


@router.post("/{conversation_id}/messages/jobs/{job_id}/cancel")
async def cancel_message_job_for_conversation(conversation_id: str, job_id: str) -> dict:
    return {"success": True, "data": cancel_conversation_message_job(conversation_id, job_id)}
