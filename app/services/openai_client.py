from openai import OpenAI

from app.core.config import settings
from app.core.errors import AppError

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if not settings.openai_api_key:
        raise AppError(503, "OpenAI API key is not configured (OPENAI_API_KEY)")
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client
