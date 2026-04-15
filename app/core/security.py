from fastapi import Header

from app.core.config import settings
from app.core.errors import AppError


async def require_internal_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = (settings.internal_api_key or "").strip()
    actual = (x_api_key or "").strip()
    if not expected or actual != expected:
        raise AppError(401, "Unauthorized")
