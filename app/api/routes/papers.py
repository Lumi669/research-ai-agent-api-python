from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.papers import ComparePdfArticlesBody, ExtractPaperBody, ReadPdfArticleBody, SummarizePaperBody
from app.services.papers import compare_pdf_articles, extract_paper, summarize_paper
from app.services.pdf_reader import read_pdf_article

router = APIRouter(prefix="/v1/papers", tags=["papers"], dependencies=[Depends(require_internal_api_key)])


@router.post("/summarize")
async def post_summarize_paper(body: SummarizePaperBody) -> dict:
    return {"success": True, "data": await summarize_paper(body)}


@router.post("/extract")
async def post_extract_paper(body: ExtractPaperBody) -> dict:
    return {"success": True, "data": await extract_paper(body)}


@router.post("/read-pdf")
async def post_read_pdf_article(body: ReadPdfArticleBody) -> dict:
    return {"success": True, "data": await read_pdf_article(str(body.pdf_url), body.title, body.max_chars)}


@router.post("/compare-pdfs")
async def post_compare_pdf_articles(body: ComparePdfArticlesBody) -> dict:
    return {"success": True, "data": await compare_pdf_articles(body)}
