from fastapi import APIRouter, Depends, Query

from app.core.security import require_internal_api_key
from app.services.usage import get_usage_summary, list_usage_events

router = APIRouter(prefix="/v1/usage", tags=["usage"], dependencies=[Depends(require_internal_api_key)])


@router.get("/summary")
async def usage_summary() -> dict:
    return {"success": True, "data": get_usage_summary()}


@router.get("/events")
async def usage_events(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    return {"success": True, "data": list_usage_events(limit)}
