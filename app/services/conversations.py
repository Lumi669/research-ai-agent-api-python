from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4

from boto3.dynamodb.conditions import Attr, Key

from app.core.errors import AppError
from app.models.agent import AgentChatBody, AgentMessage, TextPart
from app.models.conversations import ConversationDetail, ConversationSummary, CreateConversationBody, PostConversationMessageData
from app.services.agent import chat_with_agent
from app.services.dynamodb import get_dynamodb_table

CONVERSATION_META_SK = "META"
MESSAGE_SK_PREFIX = "MSG#"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _conversation_pk(conversation_id: str) -> str:
    return f"CONV#{conversation_id}"


def _message_sk(position: int) -> str:
    return f"{MESSAGE_SK_PREFIX}{position:09d}"


def _deserialize_int(value: object, default: int = 0) -> int:
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, int):
        return value
    return default


def _summary_from_item(item: dict[str, object]) -> ConversationSummary:
    return ConversationSummary(
        id=str(item["conversation_id"]),
        title=item.get("title"),
        systemPrompt=item.get("system_prompt"),
        createdAt=str(item["created_at"]),
        updatedAt=str(item["updated_at"]),
        messageCount=_deserialize_int(item.get("message_count")),
    )


def _message_from_item(item: dict[str, object]) -> AgentMessage:
    payload = {
        "role": str(item["role"]),
        "content": item.get("content"),
        "parts": item.get("parts"),
    }
    return AgentMessage.model_validate(payload)


def _detail_from_items(meta_item: dict[str, object], message_items: list[dict[str, object]]) -> ConversationDetail:
    sorted_messages = sorted(message_items, key=lambda item: _deserialize_int(item.get("position")))
    return ConversationDetail(
        id=str(meta_item["conversation_id"]),
        title=meta_item.get("title"),
        systemPrompt=meta_item.get("system_prompt"),
        createdAt=str(meta_item["created_at"]),
        updatedAt=str(meta_item["updated_at"]),
        messageCount=_deserialize_int(meta_item.get("message_count")),
        messages=[_message_from_item(item) for item in sorted_messages],
    )


async def create_conversation(body: CreateConversationBody) -> ConversationDetail:
    conversation_id = str(uuid4())
    now_iso = _now_iso()
    item = {
        "pk": _conversation_pk(conversation_id),
        "sk": CONVERSATION_META_SK,
        "entity_type": "conversation",
        "conversation_id": conversation_id,
        "title": _normalize_optional(body.title),
        "system_prompt": _normalize_optional(body.system_prompt),
        "created_at": now_iso,
        "updated_at": now_iso,
        "message_count": 0,
    }

    await asyncio.to_thread(get_dynamodb_table().put_item, Item=item)
    return ConversationDetail(
        id=conversation_id,
        title=item["title"],
        systemPrompt=item["system_prompt"],
        createdAt=now_iso,
        updatedAt=now_iso,
        messageCount=0,
        messages=[],
    )


async def list_conversations() -> list[ConversationSummary]:
    response = await asyncio.to_thread(
        get_dynamodb_table().scan,
        FilterExpression=Attr("entity_type").eq("conversation"),
    )
    items = response.get("Items", [])
    summaries = [_summary_from_item(item) for item in items]
    return sorted(summaries, key=lambda item: item.updated_at, reverse=True)


async def get_conversation(conversation_id: str) -> ConversationDetail:
    response = await asyncio.to_thread(
        get_dynamodb_table().query,
        KeyConditionExpression=Key("pk").eq(_conversation_pk(conversation_id)),
    )
    items = response.get("Items", [])
    if not items:
        raise AppError(404, "Conversation not found.")

    meta_item = next((item for item in items if item.get("sk") == CONVERSATION_META_SK), None)
    if meta_item is None:
        raise AppError(404, "Conversation not found.")

    message_items = [item for item in items if str(item.get("sk", "")).startswith(MESSAGE_SK_PREFIX)]
    return _detail_from_items(meta_item, message_items)


async def post_conversation_message(
    conversation_id: str,
    content: str | None = None,
    parts: list[dict[str, object]] | list[object] | None = None,
) -> PostConversationMessageData:
    conversation = await get_conversation(conversation_id)
    user_message_model = AgentMessage(
        role="user",
        content=content.strip() if content else None,
        parts=parts,  # type: ignore[arg-type]
    )
    user_content = user_message_model.text_content
    if not user_content:
        raise AppError(400, "Message content is required.")

    next_position = len(conversation.messages)
    user_message = {
        "pk": _conversation_pk(conversation_id),
        "sk": _message_sk(next_position),
        "entity_type": "message",
        "conversation_id": conversation_id,
        "position": next_position,
        "role": "user",
        "content": user_message_model.content,
        "parts": user_message_model.model_dump(mode="json").get("parts"),
        "created_at": _now_iso(),
    }
    await asyncio.to_thread(get_dynamodb_table().put_item, Item=user_message)

    agent_messages: list[dict[str, str]] = []
    if conversation.system_prompt:
        agent_messages.append({"role": "system", "content": conversation.system_prompt})
    agent_messages.extend({"role": message.role, "content": message.text_content} for message in conversation.messages)
    agent_messages.append({"role": "user", "content": user_content})

    assistant = await chat_with_agent(AgentChatBody(messages=agent_messages))
    assistant_message_model = AgentMessage(role="assistant", parts=[TextPart(type="text", text=assistant.reply)])
    assistant_message = {
        "pk": _conversation_pk(conversation_id),
        "sk": _message_sk(next_position + 1),
        "entity_type": "message",
        "conversation_id": conversation_id,
        "position": next_position + 1,
        "role": "assistant",
        "content": assistant_message_model.content,
        "parts": assistant_message_model.model_dump(mode="json").get("parts"),
        "created_at": _now_iso(),
    }
    await asyncio.to_thread(get_dynamodb_table().put_item, Item=assistant_message)

    updated_title = conversation.title or user_content[:80]
    updated_at = _now_iso()
    await asyncio.to_thread(
        get_dynamodb_table().update_item,
        Key={"pk": _conversation_pk(conversation_id), "sk": CONVERSATION_META_SK},
        UpdateExpression="SET title = :title, updated_at = :updated_at, message_count = :message_count",
        ExpressionAttributeValues={
            ":title": updated_title,
            ":updated_at": updated_at,
            ":message_count": len(conversation.messages) + 2,
        },
    )

    return PostConversationMessageData(conversation=await get_conversation(conversation_id), assistant=assistant)
