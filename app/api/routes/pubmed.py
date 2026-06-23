from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.pubmed import PubMedSearchBody
from app.services.pubmed import search_pubmed

router = APIRouter(prefix="/v1/pubmed", tags=["pubmed"], dependencies=[Depends(require_internal_api_key)])


@router.post("/search")
async def post_pubmed_search(body: PubMedSearchBody) -> dict:
    return {"success": True, "data": await search_pubmed(body)}
