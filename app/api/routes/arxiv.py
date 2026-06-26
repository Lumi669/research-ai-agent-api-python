from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.arxiv import ArxivSearchBody
from app.services.arxiv import search_arxiv

router = APIRouter(prefix="/v1/arxiv", tags=["arxiv"], dependencies=[Depends(require_internal_api_key)])


@router.post("/search")
async def post_arxiv_search(body: ArxivSearchBody) -> dict:
    return {"success": True, "data": await search_arxiv(body)}
