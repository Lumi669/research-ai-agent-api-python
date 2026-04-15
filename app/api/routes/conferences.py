from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.conferences import AnalyzeConferenceBody
from app.services.conference import analyze_conference
from app.services.jobs import create_conference_analysis_job, get_conference_analysis_job

router = APIRouter(prefix="/v1/conferences", tags=["conferences"], dependencies=[Depends(require_internal_api_key)])


@router.post("/analyze")
async def post_analyze_conference(body: AnalyzeConferenceBody) -> dict:
    return {"success": True, "data": await analyze_conference(body)}


@router.post("/analyze/jobs", status_code=202)
async def post_analyze_conference_job(body: AnalyzeConferenceBody) -> dict:
    return {"success": True, "data": create_conference_analysis_job(body)}


@router.get("/analyze/jobs/{job_id}")
async def get_analyze_conference_job(job_id: str) -> dict:
    return {"success": True, "data": get_conference_analysis_job(job_id)}
