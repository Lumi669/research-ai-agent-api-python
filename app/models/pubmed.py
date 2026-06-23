from pydantic import BaseModel, Field


class PubMedSearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=25)
    sort: str = Field(default="relevance", max_length=50)


class PubMedArticle(BaseModel):
    pmid: str
    title: str
    journal: str | None = None
    pub_date: str | None = Field(default=None, alias="pubDate")
    authors: list[str] = Field(default_factory=list)
    publication_types: list[str] = Field(default_factory=list, alias="publicationTypes")
    abstract: str | None = None
    url: str
    doi: str | None = None

    model_config = {"populate_by_name": True}


class PubMedSearchData(BaseModel):
    query: str
    total_results: int = Field(alias="totalResults")
    returned_results: int = Field(alias="returnedResults")
    articles: list[PubMedArticle]
    limitations: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
