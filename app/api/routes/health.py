from datetime import datetime, UTC

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    agent_mode = "mock" if settings.mock_openai else settings.agent_provider.strip().lower() or "openai"
    return {
        "status": "ok",
        "service": "ResearchAIAgentAPI-Python",
        "timestamp": datetime.now(UTC).isoformat(),
        "agentMode": agent_mode,
        "openaiConfigured": bool(settings.openai_api_key),
    }
