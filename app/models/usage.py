from typing import Literal
from pydantic import BaseModel


UsageProvider = Literal["openai", "mock"]


class UsageEvent(BaseModel):
    id: str
    route: str
    operation: str
    provider: UsageProvider
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    created_at: str


class RouteUsageSummary(BaseModel):
    route: str
    events: int
    total_tokens: int
    total_estimated_cost_usd: float


class ProviderUsageSummary(BaseModel):
    provider: UsageProvider
    events: int
    total_tokens: int
    total_estimated_cost_usd: float


class UsageSummary(BaseModel):
    total_events: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_estimated_cost_usd: float
    by_route: list[RouteUsageSummary]
    by_provider: list[ProviderUsageSummary]
