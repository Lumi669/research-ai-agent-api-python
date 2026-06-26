from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from boto3.dynamodb.conditions import Attr, Key
from openai import APIError

from app.core.config import settings
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
from app.services.openai_client import get_openai_client
from app.services.s3 import delete_conversation_prefix, delete_s3_objects, extract_s3_objects, validate_s3_message_parts

CONVERSATION_META_SK = "META"
MESSAGE_SK_PREFIX = "MSG#"
RECENT_MESSAGE_WINDOW = 8
MEMORY_ACTIVE_TOPIC_MAX_CHARS = 180
MEMORY_SUMMARY_MAX_CHARS = 2_400
_conversation_message_jobs: dict[str, ConversationMessageJob] = {}
_conversation_job_tasks: dict[str, asyncio.Task[None]] = {}
ProgressCallback = Callable[[str], None]


@dataclass
class ConversationMemoryState:
    active_topic: str | None = None
    summary: str | None = None
    last_summarized_position: int = 0


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


def _memory_from_item(item: dict[str, object]) -> ConversationMemoryState:
    active_topic = item.get("active_topic")
    summary = item.get("memory_summary")
    return ConversationMemoryState(
        active_topic=str(active_topic).strip() if isinstance(active_topic, str) and active_topic.strip() else None,
        summary=str(summary).strip() if isinstance(summary, str) and summary.strip() else None,
        last_summarized_position=_deserialize_int(item.get("last_summarized_position")),
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


def _conversation_and_memory_from_items(
    meta_item: dict[str, object],
    message_items: list[dict[str, object]],
) -> tuple[ConversationDetail, ConversationMemoryState]:
    return _detail_from_items(meta_item, message_items), _memory_from_item(meta_item)


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


def _trim_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped if len(stripped) <= max_chars else stripped[: max_chars - 3].rstrip() + "..."


def _format_messages_for_memory(messages: list[AgentMessage], start: int, end: int) -> str:
    formatted: list[str] = []
    for index, message in enumerate(messages[start:end], start=start):
        text = message.text_content.strip()
        if not text:
            continue
        formatted.append(f"[{index}] {message.role}: {text}")
    return "\n\n".join(formatted)


def _infer_active_topic_from_text(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None
    for sentence in re.split(r"(?<=[.!?])\s+", normalized):
        candidate = sentence.strip(" .:-")
        if len(candidate) >= 12:
            return _trim_text(candidate, MEMORY_ACTIVE_TOPIC_MAX_CHARS)
    return _trim_text(normalized, MEMORY_ACTIVE_TOPIC_MAX_CHARS)


def _merge_summary(existing_summary: str | None, addition: str) -> str:
    sections = [section.strip() for section in [existing_summary, addition] if section and section.strip()]
    merged = "\n".join(sections)
    return _trim_text(merged, MEMORY_SUMMARY_MAX_CHARS) or ""


def _build_memory_system_message(memory: ConversationMemoryState) -> str | None:
    fragments: list[str] = []
    if memory.active_topic:
        fragments.append(f"Active research topic: {memory.active_topic}")
    if memory.summary:
        fragments.append(f"Relevant conversation memory:\n{memory.summary}")
    if not fragments:
        return None
    return (
        "Use this hidden conversation memory to stay consistent across turns. "
        "Treat it as background context, not something to quote unless the user asks.\n\n"
        + "\n\n".join(fragments)
    )


def _parse_memory_response(content: str) -> ConversationMemoryState:
    try:
        raw = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise AppError(502, "The memory summarizer returned invalid JSON.") from exc

    active_topic = _trim_text(raw.get("active_topic") if isinstance(raw, dict) else None, MEMORY_ACTIVE_TOPIC_MAX_CHARS)
    summary = _trim_text(raw.get("summary") if isinstance(raw, dict) else None, MEMORY_SUMMARY_MAX_CHARS)
    return ConversationMemoryState(active_topic=active_topic, summary=summary)


def _summarize_memory_mock(
    memory: ConversationMemoryState,
    messages: list[AgentMessage],
    start: int,
    end: int,
) -> ConversationMemoryState:
    transcript = _format_messages_for_memory(messages, start, end)
    active_topic = memory.active_topic or _infer_active_topic_from_text(transcript)
    relevant_lines: list[str] = []
    for line in transcript.split("\n\n"):
        normalized = line.lower()
        if any(token in normalized for token in ("paper", "dataset", "method", "result", "compare", "conference", "pdf", "topic", "question")):
            relevant_lines.append(re.sub(r"^\[\d+\]\s+", "", line))
    if not relevant_lines:
        relevant_lines = [re.sub(r"^\[\d+\]\s+", "", line) for line in transcript.split("\n\n")[:3] if line.strip()]
    addition = "\n".join(f"- {line}" for line in relevant_lines[:6])
    summary = _merge_summary(memory.summary, addition)
    return ConversationMemoryState(active_topic=active_topic, summary=summary)


def _memory_system_prompt() -> str:
    return (
        "You maintain hidden long-term memory for a research assistant conversation. "
        "Keep only information that remains relevant to the active research topic and future turns. "
        "Ignore greetings, filler, duplicate phrasing, tool chatter, and off-topic detours. "
        "Prefer durable facts such as user goals, papers discussed, comparisons made, conclusions, limitations, and open questions. "
        "If the active topic has shifted, update it. "
        "Return JSON with exactly two string keys: active_topic and summary."
    )


def _memory_user_prompt(memory: ConversationMemoryState, messages: list[AgentMessage], start: int, end: int) -> str:
    existing_topic = memory.active_topic or "None"
    existing_summary = memory.summary or "None"
    transcript = _format_messages_for_memory(messages, start, end)
    return (
        f"Current active topic:\n{existing_topic}\n\n"
        f"Existing relevant memory summary:\n{existing_summary}\n\n"
        "New conversation segment to compress:\n"
        f"{transcript or 'None'}\n\n"
        "Update the memory so it keeps only information relevant to the active topic or likely future follow-up questions. "
        f"Keep active_topic under {MEMORY_ACTIVE_TOPIC_MAX_CHARS} characters and summary under {MEMORY_SUMMARY_MAX_CHARS} characters."
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
        "active_topic": None,
        "memory_summary": None,
        "last_summarized_position": 0,
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
    conversation, _memory = _conversation_and_memory_from_items(meta_item, message_items)
    return conversation


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


async def _update_conversation_memory(conversation_id: str, memory: ConversationMemoryState) -> None:
    await asyncio.to_thread(
        get_dynamodb_table().update_item,
        Key={"pk": _conversation_pk(conversation_id), "sk": CONVERSATION_META_SK},
        UpdateExpression=(
            "SET active_topic = :active_topic, memory_summary = :memory_summary, "
            "last_summarized_position = :last_summarized_position, updated_at = :updated_at"
        ),
        ExpressionAttributeValues={
            ":active_topic": memory.active_topic,
            ":memory_summary": memory.summary,
            ":last_summarized_position": memory.last_summarized_position,
            ":updated_at": _now_iso(),
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


async def _load_conversation_with_memory(conversation_id: str) -> tuple[ConversationDetail, ConversationMemoryState]:
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
    return _conversation_and_memory_from_items(meta_item, message_items)


async def _build_agent_messages(conversation_id: str) -> tuple[ConversationDetail, list[dict[str, str]]]:
    conversation, memory = await _load_conversation_with_memory(conversation_id)
    agent_messages: list[dict[str, str]] = []
    if conversation.system_prompt:
        agent_messages.append({"role": "system", "content": conversation.system_prompt})
    memory_message = _build_memory_system_message(memory)
    if memory_message:
        agent_messages.append({"role": "system", "content": memory_message})
    recent_messages = conversation.messages[memory.last_summarized_position :]
    agent_messages.extend({"role": message.role, "content": message.text_content} for message in recent_messages)
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


async def _summarize_conversation_memory(
    memory: ConversationMemoryState,
    messages: list[AgentMessage],
    start: int,
    end: int,
) -> ConversationMemoryState:
    if start >= end:
        return memory

    if settings.mock_openai:
        return _summarize_memory_mock(memory, messages, start, end)

    client = get_openai_client()
    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.openai_model,
            temperature=0.1,
            max_completion_tokens=700,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _memory_system_prompt()},
                {"role": "user", "content": _memory_user_prompt(memory, messages, start, end)},
            ],
        )
    except APIError as exc:
        raise AppError(502, f"OpenAI memory summarization failed ({exc.status_code or 'error'}): {exc.message}") from exc

    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise AppError(502, "The memory summarizer returned an empty response.")

    return _parse_memory_response(content)


async def _refresh_conversation_memory(conversation_id: str) -> None:
    conversation, memory = await _load_conversation_with_memory(conversation_id)
    cutoff = max(0, len(conversation.messages) - RECENT_MESSAGE_WINDOW)
    if cutoff <= memory.last_summarized_position:
        if not memory.active_topic and conversation.messages:
            inferred_topic = _infer_active_topic_from_text(conversation.messages[-1].text_content)
            if inferred_topic:
                memory.active_topic = inferred_topic
                await _update_conversation_memory(conversation_id, memory)
        return

    updated_memory = await _summarize_conversation_memory(
        memory,
        conversation.messages,
        memory.last_summarized_position,
        cutoff,
    )
    updated_memory.last_summarized_position = cutoff
    if not updated_memory.active_topic:
        updated_memory.active_topic = memory.active_topic or _infer_active_topic_from_text(
            conversation.messages[-1].text_content if conversation.messages else ""
        )
    await _update_conversation_memory(conversation_id, updated_memory)


async def _complete_conversation_message(
    conversation_id: str,
    *,
    content: str | None,
    parts: list[dict[str, object]] | list[object] | None,
    progress: ProgressCallback | None = None,
) -> PostConversationMessageData:
    initial_conversation = await get_conversation(conversation_id)
    if progress:
        progress("Saving user message...")
    await _store_user_message(initial_conversation, content=content, parts=parts)
    if progress:
        progress("Analyzing conversation context...")
    _conversation, agent_messages = await _build_agent_messages(conversation_id)
    if progress:
        # This is an application lifecycle update, not model reasoning or chain of thought.
        progress("Generating final answer...")
    assistant = await chat_with_agent(AgentChatBody(messages=agent_messages))
    if progress:
        progress("Saving assistant response...")
    latest_conversation = await get_conversation(conversation_id)
    await _store_assistant_message(latest_conversation, assistant.reply)
    try:
        if progress:
            progress("Updating conversation memory...")
        await _refresh_conversation_memory(conversation_id)
    except Exception:
        # Memory compression is a hidden optimization and should not fail the user-visible chat turn.
        pass
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


def _record_conversation_job_progress(job: ConversationMessageJob, message: str) -> None:
    # Progress messages are generated by backend lifecycle events only; they never expose LLM reasoning.
    if not job.progress or job.progress[-1] != message:
        job.progress.append(message)
    job.updated_at = _now_iso()


async def _run_conversation_message_job(job_id: str, conversation_id: str, body: PostConversationMessageBody) -> None:
    job = _conversation_message_jobs.get(job_id)
    if job is None:
        return

    job.status = "running"
    job.updated_at = _now_iso()
    _record_conversation_job_progress(job, "Assistant job started...")
    try:
        job.result = await _complete_conversation_message(
            conversation_id,
            content=body.content,
            parts=body.parts,
            progress=lambda message: _record_conversation_job_progress(job, message),
        )
        job.status = "succeeded"
        job.updated_at = _now_iso()
        _record_conversation_job_progress(job, "Done.")
    except asyncio.CancelledError:
        job.status = "canceled"
        job.updated_at = _now_iso()
        _record_conversation_job_progress(job, "Request canceled.")
        raise
    except AppError as exc:
        job.status = "failed"
        job.updated_at = _now_iso()
        job.error = exc.message
        _record_conversation_job_progress(job, "Request failed.")
    except Exception as exc:
        job.status = "failed"
        job.updated_at = _now_iso()
        job.error = str(exc)
        _record_conversation_job_progress(job, "Request failed.")
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
        progress=["Received request..."],
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
