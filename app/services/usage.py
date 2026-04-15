from collections import defaultdict
from datetime import datetime, UTC
from uuid import uuid4

from app.models.usage import UsageEvent, UsageSummary, RouteUsageSummary, ProviderUsageSummary, UsageProvider

MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.5, "output": 10.0},
}

_usage_events: list[UsageEvent] = []


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
    return event


def list_usage_events(limit: int = 20) -> list[UsageEvent]:
    return _usage_events[:limit]


def get_usage_summary() -> UsageSummary:
    by_route: dict[str, dict[str, float | int]] = defaultdict(lambda: {"events": 0, "total_tokens": 0, "total_estimated_cost_usd": 0.0})
    by_provider: dict[str, dict[str, float | int]] = defaultdict(lambda: {"events": 0, "total_tokens": 0, "total_estimated_cost_usd": 0.0})

    for event in _usage_events:
        by_route[event.route]["events"] += 1
        by_route[event.route]["total_tokens"] += event.total_tokens
        by_route[event.route]["total_estimated_cost_usd"] = round(by_route[event.route]["total_estimated_cost_usd"] + event.estimated_cost_usd, 8)

        by_provider[event.provider]["events"] += 1
        by_provider[event.provider]["total_tokens"] += event.total_tokens
        by_provider[event.provider]["total_estimated_cost_usd"] = round(by_provider[event.provider]["total_estimated_cost_usd"] + event.estimated_cost_usd, 8)

    return UsageSummary(
        total_events=len(_usage_events),
        total_prompt_tokens=sum(event.prompt_tokens for event in _usage_events),
        total_completion_tokens=sum(event.completion_tokens for event in _usage_events),
        total_tokens=sum(event.total_tokens for event in _usage_events),
        total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in _usage_events), 8),
        by_route=[RouteUsageSummary(route=route, **bucket) for route, bucket in by_route.items()],
        by_provider=[ProviderUsageSummary(provider=provider, **bucket) for provider, bucket in by_provider.items()],
    )
