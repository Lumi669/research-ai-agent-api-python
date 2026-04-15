from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


Mode = Literal["short", "standard"]


class AnalyzeConferenceBody(BaseModel):
    conference: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl = Field(alias="sourceUrl")
    mode: Mode = "standard"
    max_papers: int = Field(default=8, alias="maxPapers", ge=1, le=20)
    max_paper_chars: int = Field(default=2500, alias="maxPaperChars", ge=500, le=6000)

    model_config = {"populate_by_name": True}


class ConferencePaperSnapshot(BaseModel):
    title: str
    url: str
    excerpt: str


class AnalyzeConferenceData(BaseModel):
    conference: str
    source_url: HttpUrl = Field(alias="sourceUrl")
    total_papers_discovered: int = Field(alias="totalPapersDiscovered")
    papers_analyzed: int = Field(alias="papersAnalyzed")
    papers: list[ConferencePaperSnapshot]
    overview: str
    key_findings: list[str] = Field(alias="keyFindings")
    common_themes: list[str] = Field(alias="commonThemes")
    notable_papers: list[str] = Field(alias="notablePapers")
    limitations: list[str]

    model_config = {"populate_by_name": True}


ConferenceAnalysisJobStatus = Literal["queued", "running", "succeeded", "failed"]


class ConferenceAnalysisJob(BaseModel):
    job_id: str = Field(alias="jobId")
    conference: str
    source_url: HttpUrl = Field(alias="sourceUrl")
    status: ConferenceAnalysisJobStatus
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    result: AnalyzeConferenceData | None = None
    error: str | None = None

    model_config = {"populate_by_name": True}
