import json
import re

from openai import APIError

from app.core.config import settings
from app.core.errors import AppError
from app.models.papers import (
    ComparePdfArticlesBody,
    ComparePdfArticlesData,
    ComparePdfPaper,
    ExtractPaperBody,
    ExtractPaperData,
    SummarizePaperBody,
    SummarizePaperData,
)
from app.services.mock_ai import compare_pdf_articles_mock, extract_paper_mock, summarize_paper_mock
from app.services.openai_client import get_openai_client
from app.services.pdf_reader import read_pdf_article
from app.services.usage import record_usage_event

CONFIDENCE_NOTES_MAX_CHARS = 400


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise AppError(502, "The model returned text that was not valid JSON. Please retry the request.") from exc


def _summary_short_max(mode: str) -> int:
    return 280 if mode == "short" else 720


def _summarize_system_prompt(max_chars: int) -> str:
    return (
        "You summarize academic papers into structured JSON. Return exactly the keys: "
        "title, problem, method, contribution, summary_short, confidence_notes. "
        f"summary_short must be at most {max_chars} characters and confidence_notes at most {CONFIDENCE_NOTES_MAX_CHARS} characters."
    )


def _summarize_user_prompt(body: SummarizePaperBody, max_chars: int) -> str:
    return f"Title: {body.title or 'Unknown'}\nMode: {body.mode}\nsummary_short_max: {max_chars}\n\nPaper text:\n{body.text}"


def _extract_system_prompt() -> str:
    return "Extract structured paper metadata as JSON with keys: title, keywords, datasets, metrics, limitations."


def _extract_user_prompt(body: ExtractPaperBody) -> str:
    return f"Title: {body.title or 'Unknown'}\n\nPaper text:\n{body.text}"


def _compare_system_prompt() -> str:
    return "Compare two research papers using JSON with keys: overview, similarities, differences, recommendation, limitations."


def _compare_user_prompt(body: ComparePdfArticlesBody, left_text: str, right_text: str) -> str:
    return (
        f"Focus: {body.focus or 'general comparison'}\n\n"
        f"Paper A URL: {body.left.pdf_url}\n{left_text}\n\n"
        f"Paper B URL: {body.right.pdf_url}\n{right_text}"
    )


async def summarize_paper(body: SummarizePaperBody) -> SummarizePaperData:
    if settings.mock_openai:
        record_usage_event("/v1/papers/summarize", "summarizePaper", "mock", settings.openai_model, 0, 0)
        return summarize_paper_mock(body)

    client = get_openai_client()
    max_chars = _summary_short_max(body.mode)
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_completion_tokens=1000 if body.mode == "short" else 2200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _summarize_system_prompt(max_chars)},
                {"role": "user", "content": _summarize_user_prompt(body, max_chars)},
            ],
        )
    except APIError as exc:
        raise AppError(502, f"OpenAI request failed ({exc.status_code or 'error'}): {exc.message}") from exc

    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise AppError(502, "The model returned an empty response. Please retry.")

    raw = _parse_json(content)
    data = SummarizePaperData(**raw)
    record_usage_event("/v1/papers/summarize", "summarizePaper", "openai", settings.openai_model, completion.usage.prompt_tokens if completion.usage else 0, completion.usage.completion_tokens if completion.usage else 0)
    return data


async def extract_paper(body: ExtractPaperBody) -> ExtractPaperData:
    if settings.mock_openai:
        record_usage_event("/v1/papers/extract", "extractPaper", "mock", settings.openai_model, 0, 0)
        return extract_paper_mock(body)

    client = get_openai_client()
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            max_completion_tokens=1800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _extract_system_prompt()},
                {"role": "user", "content": _extract_user_prompt(body)},
            ],
        )
    except APIError as exc:
        raise AppError(502, f"OpenAI request failed ({exc.status_code or 'error'}): {exc.message}") from exc

    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise AppError(502, "The model returned an empty response. Please retry.")

    data = ExtractPaperData(**_parse_json(content))
    record_usage_event("/v1/papers/extract", "extractPaper", "openai", settings.openai_model, completion.usage.prompt_tokens if completion.usage else 0, completion.usage.completion_tokens if completion.usage else 0)
    return data


async def compare_pdf_articles(body: ComparePdfArticlesBody) -> ComparePdfArticlesData:
    left = await read_pdf_article(str(body.left.pdf_url), body.left.title, body.max_chars_per_paper)
    right = await read_pdf_article(str(body.right.pdf_url), body.right.title, body.max_chars_per_paper)

    if settings.mock_openai:
        record_usage_event("/v1/papers/compare-pdfs", "comparePdfArticles", "mock", settings.openai_model, 0, 0)
        return compare_pdf_articles_mock(body, left, right)

    client = get_openai_client()
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_completion_tokens=900 if body.mode == "short" else 1800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _compare_system_prompt()},
                {"role": "user", "content": _compare_user_prompt(body, left.text, right.text)},
            ],
        )
    except APIError as exc:
        raise AppError(502, f"OpenAI request failed ({exc.status_code or 'error'}): {exc.message}") from exc

    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise AppError(502, "The model returned an empty comparison response. Please retry.")

    raw = _parse_json(content)
    record_usage_event("/v1/papers/compare-pdfs", "comparePdfArticles", "openai", settings.openai_model, completion.usage.prompt_tokens if completion.usage else 0, completion.usage.completion_tokens if completion.usage else 0)
    return ComparePdfArticlesData(
        focus=body.focus,
        papers=[
            ComparePdfPaper(title=left.title, pdfUrl=str(left.pdf_url), pageCount=left.page_count, truncated=left.truncated),
            ComparePdfPaper(title=right.title, pdfUrl=str(right.pdf_url), pageCount=right.page_count, truncated=right.truncated),
        ],
        overview=raw.get("overview", ""),
        similarities=raw.get("similarities", []),
        differences=raw.get("differences", []),
        recommendation=raw.get("recommendation", ""),
        limitations=raw.get("limitations", []),
    )
