from io import BytesIO
import re

import httpx
from pypdf import PdfReader

from app.core.errors import AppError
from app.models.papers import ReadPdfArticleData, ReadPdfArticleMetadata


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip())


def _split_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[;,]", raw) if part.strip()][:20]


async def read_pdf_article(pdf_url: str, title: str | None = None, max_chars: int = 20_000) -> ReadPdfArticleData:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(pdf_url)
    if response.status_code >= 400:
        raise AppError(502, f"Failed to fetch PDF from {pdf_url}: HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
        raise AppError(422, "The provided URL does not appear to be a PDF.")

    try:
        reader = PdfReader(BytesIO(response.content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise AppError(502, "Failed to parse PDF content.") from exc

    text = _normalize_text(text)
    if not text:
        raise AppError(422, "The PDF was fetched, but no readable text could be extracted.")

    metadata = reader.metadata or {}
    resolved_title = title or getattr(metadata, "title", None) or text.splitlines()[0][:300]
    limited = text[:max_chars]
    return ReadPdfArticleData(
        title=resolved_title,
        pdfUrl=pdf_url,
        pageCount=len(reader.pages),
        text=limited,
        totalCharacters=len(text),
        truncated=len(text) > len(limited),
        metadata=ReadPdfArticleMetadata(
            author=getattr(metadata, "author", None),
            subject=getattr(metadata, "subject", None),
            keywords=_split_keywords(getattr(metadata, "keywords", None)),
        ),
    )
