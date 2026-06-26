from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.cvf import CVFSearchBody
from app.services.cvf import search_cvf

router = APIRouter(prefix="/v1/cvf", tags=["cvf"], dependencies=[Depends(require_internal_api_key)])


@router.post("/search")
async def post_cvf_search(body: CVFSearchBody) -> dict:
    return {"success": True, "data": await search_cvf(body)}
