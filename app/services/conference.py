import html
import json
import re
from urllib.parse import urljoin, urlparse

import httpx
from openai import APIError

from app.core.config import settings
from app.core.errors import AppError
from app.models.conferences import AnalyzeConferenceBody, AnalyzeConferenceData, ConferencePaperSnapshot
from app.services.mock_ai import analyze_conference_mock
from app.services.openai_client import get_openai_client
from app.services.usage import record_usage_event

LISTING_TEXT_MAX_CHARS = 6000


def _strip_html_to_text(raw_html: str) -> str:
    raw_html = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
    raw_html = re.sub(r"<style[\s\S]*?</style>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _looks_like_paper_title(text: str) -> bool:
    if len(text) < 20 or len(text) > 300:
        return False
    if len(text.split()) < 4:
        return False
    banned = ["home", "authors", "organizers", "schedule", "program", "workshop", "tutorial", "accepted papers"]
    lowered = text.lower()
    return not any(fragment == lowered or f" {fragment} " in lowered for fragment in banned)


def _extract_candidate_papers(listing_html: str, source_url: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a\b[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', listing_html, flags=re.IGNORECASE | re.DOTALL):
        href, raw_text = match.groups()
        url = urljoin(source_url, href.strip())
        title = _strip_html_to_text(raw_text)
        if not _looks_like_paper_title(title):
            continue
        searchable = f"{urlparse(url).netloc}{urlparse(url).path}{urlparse(url).query}".lower()
        paper_like = url.lower().endswith(".pdf") or any(token in searchable for token in ["/paper", "/papers", "/content", "openaccess", "forum?id="])
        if not paper_like or url in seen:
            continue
        seen.add(url)
        results.append((title, url))
    return results


async def _fetch_text(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            response = await client.get(url, headers={"user-agent": "ResearchAIAgentAPI/0.1 (+conference-analysis)"})
        except Exception as exc:
            raise AppError(502, f"Failed to fetch remote content from {url}: {exc}") from exc
    if response.status_code >= 400:
        raise AppError(502, f"Failed to fetch remote content from {url}: HTTP {response.status_code}")
    return response.text


async def _build_paper_snapshot(title: str, url: str, max_paper_chars: int) -> ConferencePaperSnapshot:
    if url.lower().endswith(".pdf"):
        return ConferencePaperSnapshot(title=title, url=url, excerpt="PDF link detected. Full text was not extracted from this URL.")
    html_text = await _fetch_text(url)
    page_text = _strip_html_to_text(html_text)
    return ConferencePaperSnapshot(title=title, url=url, excerpt=(page_text[:max_paper_chars].strip() or "No readable text extracted from the page."))


def _conference_system_prompt() -> str:
    return "Summarize conference paper trends as JSON with keys: overview, key_findings, common_themes, notable_papers, limitations."


def _conference_user_prompt(input_data: AnalyzeConferenceBody, listing_text: str, papers: list[ConferencePaperSnapshot]) -> str:
    rendered = "\n\n".join([f"Title: {paper.title}\nURL: {paper.url}\nExcerpt: {paper.excerpt}" for paper in papers])
    return f"Conference: {input_data.conference}\nSource URL: {input_data.source_url}\nListing excerpt:\n{listing_text}\n\nPaper sample:\n{rendered}"


async def analyze_conference(input_data: AnalyzeConferenceBody) -> AnalyzeConferenceData:
    listing_html = await _fetch_text(str(input_data.source_url))
    listing_text = _strip_html_to_text(listing_html)[:LISTING_TEXT_MAX_CHARS].strip()
    candidates = _extract_candidate_papers(listing_html, str(input_data.source_url))
    if not candidates:
        raise AppError(422, "No candidate paper links were found on the provided conference page. Try a page that directly lists accepted papers.")

    selected = candidates[: input_data.max_papers]
    papers: list[ConferencePaperSnapshot] = []
    for title, url in selected:
        try:
            papers.append(await _build_paper_snapshot(title, url, input_data.max_paper_chars))
        except AppError:
            continue

    if not papers:
        raise AppError(502, "Paper links were discovered, but none of the linked pages could be read successfully.")

    if settings.mock_openai:
        record_usage_event("/v1/conferences/analyze", "analyzeConference", "mock", settings.openai_model, 0, 0)
        return analyze_conference_mock(input_data, papers, len(candidates))

    client = get_openai_client()
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_completion_tokens=1200 if input_data.mode == "short" else 2200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _conference_system_prompt()},
                {"role": "user", "content": _conference_user_prompt(input_data, listing_text, papers)},
            ],
        )
    except APIError as exc:
        raise AppError(502, f"OpenAI request failed ({exc.status_code or 'error'}): {exc.message}") from exc

    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise AppError(502, "The model returned an empty response. Please retry.")
    raw = json.loads(content)
    record_usage_event("/v1/conferences/analyze", "analyzeConference", "openai", settings.openai_model, completion.usage.prompt_tokens if completion.usage else 0, completion.usage.completion_tokens if completion.usage else 0)
    return AnalyzeConferenceData(
        conference=input_data.conference,
        sourceUrl=str(input_data.source_url),
        totalPapersDiscovered=len(candidates),
        papersAnalyzed=len(papers),
        papers=papers,
        overview=raw.get("overview", ""),
        keyFindings=raw.get("key_findings", []),
        commonThemes=raw.get("common_themes", []),
        notablePapers=raw.get("notable_papers", []),
        limitations=raw.get("limitations", []),
    )
