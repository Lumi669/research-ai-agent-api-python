import asyncio
from collections import defaultdict
from datetime import datetime, UTC
import json
import logging
from pathlib import Path
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from decimal import Decimal

from app.core.config import settings
from app.models.usage import UsageEvent, UsageSummary, RouteUsageSummary, ProviderUsageSummary, UsageProvider
from app.services.dynamodb import get_dynamodb_table

MODEL_PRICING = {
    "gpt-5.4-mini": {"input": 0.75, "output": 4.5},
    "gpt-5.4": {"input": 2.5, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.5, "output": 10.0},
}

_usage_events: list[UsageEvent] = []
logger = logging.getLogger(__name__)
USAGE_PK = "USAGE"
USAGE_SK_PREFIX = "EVENT#"


def _usage_store_path() -> Path:
    return Path(settings.usage_store_path)


def _load_usage_events() -> list[UsageEvent]:
    path = _usage_store_path()
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read usage store %s: %s", path, exc)
        return []

    if not isinstance(payload, list):
        logger.warning("Usage store %s is not a JSON array; ignoring it.", path)
        return []

    events: list[UsageEvent] = []
    for item in payload:
        try:
            events.append(UsageEvent.model_validate(item))
        except Exception as exc:
            logger.warning("Skipping invalid usage event from %s: %s", path, exc)

    return events


def _save_usage_events() -> None:
    path = _usage_store_path()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([event.model_dump(mode="json") for event in _usage_events], indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to persist usage store %s: %s", path, exc)


def _usage_sk(created_at: str, usage_id: str) -> str:
    return f"{USAGE_SK_PREFIX}{created_at}#{usage_id}"


def _serialize_usage_event(event: UsageEvent) -> dict[str, object]:
    return {
        "pk": USAGE_PK,
        "sk": _usage_sk(event.created_at, event.id),
        "entity_type": "usage_event",
        "usage_id": event.id,
        "route": event.route,
        "operation": event.operation,
        "provider": event.provider,
        "model": event.model,
        "prompt_tokens": event.prompt_tokens,
        "completion_tokens": event.completion_tokens,
        "total_tokens": event.total_tokens,
        "estimated_cost_usd": Decimal(str(event.estimated_cost_usd)),
        "created_at": event.created_at,
    }


def _deserialize_int(value: object, default: int = 0) -> int:
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, int):
        return value
    return default


def _deserialize_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (float, int)):
        return float(value)
    return default


def _usage_event_from_item(item: dict[str, object]) -> UsageEvent:
    return UsageEvent(
        id=str(item.get("usage_id") or item.get("id")),
        route=str(item["route"]),
        operation=str(item["operation"]),
        provider=item["provider"],  # type: ignore[arg-type]
        model=str(item["model"]),
        prompt_tokens=_deserialize_int(item.get("prompt_tokens")),
        completion_tokens=_deserialize_int(item.get("completion_tokens")),
        total_tokens=_deserialize_int(item.get("total_tokens")),
        estimated_cost_usd=round(_deserialize_float(item.get("estimated_cost_usd")), 8),
        created_at=str(item["created_at"]),
    )


async def _store_usage_event_dynamodb(event: UsageEvent) -> None:
    await asyncio.to_thread(get_dynamodb_table().put_item, Item=_serialize_usage_event(event))


async def _list_usage_events_dynamodb(limit: int = 20) -> list[UsageEvent]:
    response = await asyncio.to_thread(
        get_dynamodb_table().query,
        KeyConditionExpression=Key("pk").eq(USAGE_PK),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [_usage_event_from_item(item) for item in response.get("Items", [])]


async def _load_all_usage_events_dynamodb() -> list[UsageEvent]:
    items: list[dict[str, object]] = []
    exclusive_start_key: dict[str, object] | None = None

    while True:
        query_kwargs = {
            "KeyConditionExpression": Key("pk").eq(USAGE_PK),
            "ScanIndexForward": False,
        }
        if exclusive_start_key:
            query_kwargs["ExclusiveStartKey"] = exclusive_start_key

        response = await asyncio.to_thread(get_dynamodb_table().query, **query_kwargs)
        items.extend(response.get("Items", []))
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break

    return [_usage_event_from_item(item) for item in items]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def estimate_usage_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model.strip().lower())
    if not pricing:
        return 0.0
    return round((prompt_tokens / 1_000_000) * pricing["input"] + (completion_tokens / 1_000_000) * pricing["output"], 8)


def record_usage_event(route: str, operation: str, provider: UsageProvider, model: str, prompt_tokens: int, completion_tokens: int) -> UsageEvent:
    event = UsageEvent(
        id=str(uuid4()),
        route=route,
        operation=operation,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=estimate_usage_cost_usd(model, prompt_tokens, completion_tokens),
        created_at=now_iso(),
    )
    _usage_events.insert(0, event)
    _save_usage_events()
    if (settings.dynamodb_table_name or "").strip():
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_store_usage_event_dynamodb(event))
        except RuntimeError:
            logger.warning("Skipping DynamoDB usage persistence because no event loop is running.")
    return event


def list_local_usage_events(limit: int = 20) -> list[UsageEvent]:
    return _usage_events[:limit]


async def list_usage_events(limit: int = 20) -> list[UsageEvent]:
    if (settings.dynamodb_table_name or "").strip():
        try:
            return await _list_usage_events_dynamodb(limit)
        except Exception as exc:
            logger.warning("Falling back to local usage events after DynamoDB read failed: %s", exc)
    return list_local_usage_events(limit)


def get_local_usage_summary() -> UsageSummary:
    return _build_usage_summary(_usage_events, source="local")


def _build_usage_summary(events: list[UsageEvent], *, source: str) -> UsageSummary:
    by_route: dict[str, dict[str, float | int]] = defaultdict(lambda: {"events": 0, "total_tokens": 0, "total_estimated_cost_usd": 0.0})
    by_provider: dict[str, dict[str, float | int]] = defaultdict(lambda: {"events": 0, "total_tokens": 0, "total_estimated_cost_usd": 0.0})

    for event in events:
        by_route[event.route]["events"] += 1
        by_route[event.route]["total_tokens"] += event.total_tokens
        by_route[event.route]["total_estimated_cost_usd"] = round(by_route[event.route]["total_estimated_cost_usd"] + event.estimated_cost_usd, 8)

        by_provider[event.provider]["events"] += 1
        by_provider[event.provider]["total_tokens"] += event.total_tokens
        by_provider[event.provider]["total_estimated_cost_usd"] = round(by_provider[event.provider]["total_estimated_cost_usd"] + event.estimated_cost_usd, 8)

    return UsageSummary(
        total_events=len(events),
        total_prompt_tokens=sum(event.prompt_tokens for event in events),
        total_completion_tokens=sum(event.completion_tokens for event in events),
        total_tokens=sum(event.total_tokens for event in events),
        total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 8),
        by_route=[RouteUsageSummary(route=route, **bucket) for route, bucket in by_route.items()],
        by_provider=[ProviderUsageSummary(provider=provider, **bucket) for provider, bucket in by_provider.items()],
        source=source,  # type: ignore[arg-type]
    )


async def get_usage_summary() -> UsageSummary:
    if (settings.dynamodb_table_name or "").strip():
        try:
            return _build_usage_summary(await _load_all_usage_events_dynamodb(), source="dynamodb")
        except Exception as exc:
            logger.warning("Falling back to local usage summary after DynamoDB read failed: %s", exc)
    return get_local_usage_summary()


_usage_events.extend(_load_usage_events())
