import asyncio
from datetime import datetime, UTC
from uuid import uuid4

from app.core.errors import AppError
from app.models.conferences import AnalyzeConferenceBody, ConferenceAnalysisJob
from app.services.conference import analyze_conference

_jobs: dict[str, ConferenceAnalysisJob] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _run_job(job_id: str, input_data: AnalyzeConferenceBody) -> None:
    current = _jobs.get(job_id)
    if not current:
        return
    current.status = "running"
    current.updated_at = _now_iso()
    try:
        current.result = await analyze_conference(input_data)
        current.status = "succeeded"
        current.updated_at = _now_iso()
    except Exception as exc:
        current.status = "failed"
        current.updated_at = _now_iso()
        current.error = str(exc)


def create_conference_analysis_job(input_data: AnalyzeConferenceBody) -> ConferenceAnalysisJob:
    timestamp = _now_iso()
    job = ConferenceAnalysisJob(
        jobId=str(uuid4()),
        conference=input_data.conference,
        sourceUrl=str(input_data.source_url),
        status="queued",
        createdAt=timestamp,
        updatedAt=timestamp,
    )
    _jobs[job.job_id] = job
    asyncio.create_task(_run_job(job.job_id, input_data))
    return job


def get_conference_analysis_job(job_id: str) -> ConferenceAnalysisJob:
    job = _jobs.get(job_id)
    if not job:
        raise AppError(404, f"Conference analysis job not found: {job_id}")
    return job
