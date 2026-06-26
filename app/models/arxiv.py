from pydantic import BaseModel, Field


class ArxivSearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=25)
    sort_by: str = Field(default="submittedDate", alias="sortBy", max_length=50)
    sort_order: str = Field(default="descending", alias="sortOrder", max_length=50)

    model_config = {"populate_by_name": True}


class ArxivArticle(BaseModel):
    arxiv_id: str = Field(alias="arxivId")
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str
    published: str | None = None
    updated: str | None = None
    categories: list[str] = Field(default_factory=list)
    url: str
    pdf_url: str | None = Field(default=None, alias="pdfUrl")
    doi: str | None = None

    model_config = {"populate_by_name": True}


class ArxivSearchData(BaseModel):
    query: str
    total_results: int | None = Field(default=None, alias="totalResults")
    returned_results: int = Field(alias="returnedResults")
    articles: list[ArxivArticle]
    limitations: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
