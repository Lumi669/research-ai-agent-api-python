from pydantic import BaseModel, Field


class CVFSearchBody(BaseModel):
    source_url: str = Field(alias="sourceUrl", min_length=1, max_length=2000)
    query: str | None = Field(default=None, max_length=500)
    limit: int = Field(default=10, ge=1, le=25)

    model_config = {"populate_by_name": True}


class CVFPaper(BaseModel):
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    event_type: str | None = Field(default=None, alias="eventType")
    session: str | None = None
    virtual_url: str | None = Field(default=None, alias="virtualUrl")
    paper_url: str | None = Field(default=None, alias="paperUrl")
    pdf_url: str | None = Field(default=None, alias="pdfUrl")

    model_config = {"populate_by_name": True}


class CVFSearchData(BaseModel):
    conference: str
    source_url: str = Field(alias="sourceUrl")
    query: str | None = None
    total_results: int = Field(alias="totalResults")
    returned_results: int = Field(alias="returnedResults")
    papers: list[CVFPaper]
    limitations: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
