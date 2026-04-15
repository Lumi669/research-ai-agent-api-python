from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator


Mode = Literal["short", "standard"]


class SummarizePaperBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    text: str = Field(min_length=1, max_length=500_000)
    mode: Mode = "standard"

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class SummarizePaperData(BaseModel):
    title: str | None
    problem: str
    method: str
    contribution: str
    summary_short: str
    confidence_notes: str


class ExtractPaperBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    text: str = Field(min_length=1, max_length=500_000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ExtractPaperData(BaseModel):
    title: str | None
    keywords: list[str]
    datasets: list[str]
    metrics: list[str]
    limitations: list[str]


class ReadPdfArticleBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    pdf_url: HttpUrl = Field(alias="pdfUrl")
    max_chars: int = Field(default=20_000, alias="maxChars", ge=500, le=200_000)

    model_config = {"populate_by_name": True}


class ReadPdfArticleMetadata(BaseModel):
    author: str | None
    subject: str | None
    keywords: list[str]


class ReadPdfArticleData(BaseModel):
    title: str | None
    pdf_url: HttpUrl = Field(alias="pdfUrl")
    page_count: int | None = Field(alias="pageCount")
    text: str
    total_characters: int = Field(alias="totalCharacters")
    truncated: bool
    metadata: ReadPdfArticleMetadata

    model_config = {"populate_by_name": True}


class PdfSource(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    pdf_url: HttpUrl = Field(alias="pdfUrl")

    model_config = {"populate_by_name": True}


class ComparePdfArticlesBody(BaseModel):
    left: PdfSource
    right: PdfSource
    focus: str | None = Field(default=None, max_length=500)
    mode: Mode = "standard"
    max_chars_per_paper: int = Field(default=12_000, alias="maxCharsPerPaper", ge=500, le=80_000)

    model_config = {"populate_by_name": True}


class ComparePdfPaper(BaseModel):
    title: str | None
    pdf_url: HttpUrl = Field(alias="pdfUrl")
    page_count: int | None = Field(alias="pageCount")
    truncated: bool

    model_config = {"populate_by_name": True}


class ComparePdfArticlesData(BaseModel):
    focus: str | None
    papers: list[ComparePdfPaper]
    overview: str
    similarities: list[str]
    differences: list[str]
    recommendation: str
    limitations: list[str]
