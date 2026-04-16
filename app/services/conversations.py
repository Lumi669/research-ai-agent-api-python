from __future__ import annotations

import asyncio
import re
from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4

from boto3.dynamodb.conditions import Attr, Key

from app.core.errors import AppError
from app.models.agent import AgentChatBody, AgentMessage, TableData, TablePart, TextPart
from app.models.conversations import (
    ConversationDetail,
    ConversationMessageJob,
    CreateConversationBody,
    ConversationSummary,
    PostConversationMessageBody,
    PostConversationMessageData,
    UpdateConversationBody,
)
from app.services.agent import chat_with_agent
from app.services.dynamodb import get_dynamodb_table
from app.services.s3 import delete_conversation_prefix, delete_s3_objects, extract_s3_objects, validate_s3_message_parts

CONVERSATION_META_SK = "META"
MESSAGE_SK_PREFIX = "MSG#"
_conversation_message_jobs: dict[str, ConversationMessageJob] = {}
_conversation_job_tasks: dict[str, asyncio.Task[None]] = {}


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


def _split_markdown_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _is_markdown_separator_row(row: str) -> bool:
    cells = _split_markdown_row(row)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _parse_assistant_parts(reply: str) -> list[object]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", reply.strip()) if block.strip()]
    if not blocks:
        return [TextPart(type="text", text=reply.strip() or "(empty)")]

    parts: list[object] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) >= 2 and "|" in lines[0] and _is_markdown_separator_row(lines[1]):
            headers = _split_markdown_row(lines[0])
            rows = [_split_markdown_row(line) for line in lines[2:]]
            normalized_rows = [row[: len(headers)] + [""] * max(0, len(headers) - len(row)) for row in rows]
            parts.append(TablePart(type="table", table=TableData(columns=headers, rows=normalized_rows)))
            continue
        parts.append(TextPart(type="text", text=block))
    return parts


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


async def update_conversation(conversation_id: str, body: UpdateConversationBody) -> ConversationDetail:
    await get_conversation(conversation_id)
    await asyncio.to_thread(
        get_dynamodb_table().update_item,
        Key={"pk": _conversation_pk(conversation_id), "sk": CONVERSATION_META_SK},
        UpdateExpression="SET title = :title, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":title": _normalize_optional(body.title),
            ":updated_at": _now_iso(),
        },
    )
    return await get_conversation(conversation_id)


async def delete_conversation(conversation_id: str) -> None:
    conversation = await get_conversation(conversation_id)
    s3_objects: list[tuple[str, str]] = []
    for message in conversation.messages:
        s3_objects.extend(extract_s3_objects(message.parts))

    await delete_s3_objects(s3_objects)
    await delete_conversation_prefix(conversation_id)

    def _delete_items() -> None:
        table = get_dynamodb_table()
        with table.batch_writer() as batch:
            batch.delete_item(Key={"pk": _conversation_pk(conversation.id), "sk": CONVERSATION_META_SK})
            for position, _message in enumerate(conversation.messages):
                batch.delete_item(Key={"pk": _conversation_pk(conversation.id), "sk": _message_sk(position)})

    await asyncio.to_thread(_delete_items)

    for job_id, job in list(_conversation_message_jobs.items()):
        if job.conversation_id != conversation_id:
            continue
        task = _conversation_job_tasks.pop(job_id, None)
        if task is not None:
            task.cancel()
        job.status = "canceled"
        job.updated_at = _now_iso()


async def _update_conversation_meta(
    conversation_id: str,
    *,
    title: str | None,
    message_count: int,
) -> None:
    await asyncio.to_thread(
        get_dynamodb_table().update_item,
        Key={"pk": _conversation_pk(conversation_id), "sk": CONVERSATION_META_SK},
        UpdateExpression="SET title = :title, updated_at = :updated_at, message_count = :message_count",
        ExpressionAttributeValues={
            ":title": title,
            ":updated_at": _now_iso(),
            ":message_count": message_count,
        },
    )


async def _store_user_message(
    conversation: ConversationDetail,
    *,
    content: str | None,
    parts: list[dict[str, object]] | list[object] | None,
) -> tuple[AgentMessage, int]:
    user_message_model = AgentMessage(
        role="user",
        content=content.strip() if content else None,
        parts=parts,  # type: ignore[arg-type]
    )
    await validate_s3_message_parts(user_message_model.parts, conversation.id)
    user_content = user_message_model.text_content
    if not user_content:
        raise AppError(400, "Message content is required.")

    next_position = len(conversation.messages)
    user_message = {
        "pk": _conversation_pk(conversation.id),
        "sk": _message_sk(next_position),
        "entity_type": "message",
        "conversation_id": conversation.id,
        "position": next_position,
        "role": "user",
        "content": user_message_model.content,
        "parts": user_message_model.model_dump(mode="json").get("parts"),
        "created_at": _now_iso(),
    }
    await asyncio.to_thread(get_dynamodb_table().put_item, Item=user_message)

    updated_title = conversation.title or user_content[:80]
    await _update_conversation_meta(conversation.id, title=updated_title, message_count=len(conversation.messages) + 1)
    return user_message_model, next_position


async def _build_agent_messages(conversation_id: str) -> tuple[ConversationDetail, list[dict[str, str]]]:
    conversation = await get_conversation(conversation_id)
    agent_messages: list[dict[str, str]] = []
    if conversation.system_prompt:
        agent_messages.append({"role": "system", "content": conversation.system_prompt})
    agent_messages.extend({"role": message.role, "content": message.text_content} for message in conversation.messages)
    return conversation, agent_messages


async def _store_assistant_message(conversation: ConversationDetail, assistant_reply: str) -> None:
    next_position = len(conversation.messages)
    assistant_parts = _parse_assistant_parts(assistant_reply)
    assistant_message_model = AgentMessage(role="assistant", parts=assistant_parts)
    assistant_message = {
        "pk": _conversation_pk(conversation.id),
        "sk": _message_sk(next_position),
        "entity_type": "message",
        "conversation_id": conversation.id,
        "position": next_position,
        "role": "assistant",
        "content": assistant_message_model.content,
        "parts": assistant_message_model.model_dump(mode="json").get("parts"),
        "created_at": _now_iso(),
    }
    await asyncio.to_thread(get_dynamodb_table().put_item, Item=assistant_message)
    await _update_conversation_meta(conversation.id, title=conversation.title, message_count=len(conversation.messages) + 1)


async def _complete_conversation_message(
    conversation_id: str,
    *,
    content: str | None,
    parts: list[dict[str, object]] | list[object] | None,
) -> PostConversationMessageData:
    initial_conversation = await get_conversation(conversation_id)
    await _store_user_message(initial_conversation, content=content, parts=parts)
    updated_conversation, agent_messages = await _build_agent_messages(conversation_id)
    assistant = await chat_with_agent(AgentChatBody(messages=agent_messages))
    latest_conversation = await get_conversation(conversation_id)
    await _store_assistant_message(latest_conversation, assistant.reply)
    return PostConversationMessageData(conversation=await get_conversation(conversation_id), assistant=assistant)


async def post_conversation_message(
    conversation_id: str,
    content: str | None = None,
    parts: list[dict[str, object]] | list[object] | None = None,
) -> PostConversationMessageData:
    return await _complete_conversation_message(conversation_id, content=content, parts=parts)


def _find_active_message_job(conversation_id: str) -> ConversationMessageJob | None:
    for job in _conversation_message_jobs.values():
        if job.conversation_id == conversation_id and job.status in {"queued", "running"}:
            return job
    return None


async def _run_conversation_message_job(job_id: str, conversation_id: str, body: PostConversationMessageBody) -> None:
    job = _conversation_message_jobs.get(job_id)
    if job is None:
        return

    job.status = "running"
    job.updated_at = _now_iso()
    try:
        job.result = await _complete_conversation_message(conversation_id, content=body.content, parts=body.parts)
        job.status = "succeeded"
        job.updated_at = _now_iso()
    except asyncio.CancelledError:
        job.status = "canceled"
        job.updated_at = _now_iso()
        raise
    except AppError as exc:
        job.status = "failed"
        job.updated_at = _now_iso()
        job.error = exc.message
    except Exception as exc:
        job.status = "failed"
        job.updated_at = _now_iso()
        job.error = str(exc)
    finally:
        _conversation_job_tasks.pop(job_id, None)


def create_conversation_message_job(conversation_id: str, body: PostConversationMessageBody) -> ConversationMessageJob:
    active_job = _find_active_message_job(conversation_id)
    if active_job is not None:
        raise AppError(409, f"A message job is already in progress for this conversation: {active_job.job_id}")

    timestamp = _now_iso()
    job = ConversationMessageJob(
        jobId=str(uuid4()),
        conversationId=conversation_id,
        status="queued",
        createdAt=timestamp,
        updatedAt=timestamp,
        request=body,
    )
    _conversation_message_jobs[job.job_id] = job
    _conversation_job_tasks[job.job_id] = asyncio.create_task(_run_conversation_message_job(job.job_id, conversation_id, body))
    return job


def get_conversation_message_job(conversation_id: str, job_id: str) -> ConversationMessageJob:
    job = _conversation_message_jobs.get(job_id)
    if job is None or job.conversation_id != conversation_id:
        raise AppError(404, f"Conversation message job not found: {job_id}")
    return job


def cancel_conversation_message_job(conversation_id: str, job_id: str) -> ConversationMessageJob:
    job = get_conversation_message_job(conversation_id, job_id)
    if job.status in {"succeeded", "failed", "canceled"}:
        return job

    task = _conversation_job_tasks.get(job_id)
    if task is not None:
        task.cancel()
    job.status = "canceled"
    job.updated_at = _now_iso()
    return job
