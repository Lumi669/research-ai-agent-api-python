import json
import re
from urllib.parse import urljoin, urlparse

import httpx

from app.core.errors import AppError
from app.models.cvf import CVFPaper, CVFSearchBody, CVFSearchData

CVF_MAX_LIMIT = 25
CVF_DEFAULT_HOST = "https://cvpr.thecvf.com"
CVF_DEFAULT_YEAR = "2026"


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_year(source_url: str) -> str:
    match = re.search(r"/virtual/(\d{4})/", source_url)
    if match:
        return match.group(1)
    if "cvpr" in source_url.lower() or "cvf" in source_url.lower():
        return CVF_DEFAULT_YEAR
    raise AppError(422, "Only CVF virtual paper URLs or CVPR/CVF natural-language prompts are supported.")


def _source_url_from_input(value: str, year: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        if "/virtual/" not in parsed.path and ("thecvf.com" in parsed.netloc or "openaccess" in parsed.netloc):
            return f"{CVF_DEFAULT_HOST}/virtual/{year}/papers.html"
        return value
    if "cvpr" in value.lower() or "cvf" in value.lower():
        return f"{CVF_DEFAULT_HOST}/virtual/{year}/papers.html"
    return value


def _conference_from_url(source_url: str, year: str) -> str:
    host = urlparse(source_url).netloc.lower()
    if "cvpr" in host or "cvpr" in source_url.lower():
        return f"CVPR {year}"
    return f"CVF {year}"


def _data_urls(source_url: str) -> tuple[str, str]:
    year = _extract_year(source_url)
    base = f"/static/virtual/data/cvpr-{year}-"
    return (
        urljoin(source_url, f"{base}orals-posters.json"),
        urljoin(source_url, f"{base}abstracts.json"),
    )


def _extract_query(source_url: str, explicit_query: str | None) -> str | None:
    if explicit_query and explicit_query.strip():
        return explicit_query.strip()
    match = re.search(r"[?&]search=([^&]*)", source_url)
    if match:
        from urllib.parse import unquote_plus

        query = unquote_plus(match.group(1)).strip()
        return query or None
    about_match = re.search(r"\babout\s+(.+?)(?:[.?!]|$)", source_url, flags=re.IGNORECASE)
    if about_match:
        query = re.sub(r"\b(first|latest|top)\s+\d+\s+papers?\b", " ", about_match.group(1), flags=re.IGNORECASE)
        query = re.sub(r"\bin\s+cvpr\b|\bcvpr\b|\bpapers?\b", " ", query, flags=re.IGNORECASE)
        return _normalize_text(query) or None
    return None


def _query_score(item: dict[str, object], abstract: str | None, query: str | None) -> int:
    if not query:
        return 1

    normalized_query = query.lower().strip()
    title = _normalize_text(item.get("name")).lower()
    keywords = " ".join(_normalize_text(keyword) for keyword in item.get("keywords", []) if keyword).lower()
    authors = " ".join(_normalize_text(author.get("fullname")) for author in item.get("authors", []) if isinstance(author, dict)).lower()
    abstract_text = _normalize_text(abstract).lower()
    haystack = " ".join([title, keywords, authors, abstract_text])
    tokens = normalized_query.split()
    if not all(token in haystack for token in tokens):
        return 0

    score = 10
    if normalized_query in title:
        score += 100
    if normalized_query in keywords:
        score += 80
    if normalized_query in abstract_text:
        score += 50
    return score


def _derive_pdf_url(paper_url: str | None) -> str | None:
    if not paper_url:
        return None
    if paper_url.endswith(".pdf"):
        return paper_url
    parsed = urlparse(paper_url)
    if "openaccess.thecvf.com" not in parsed.netloc or "/html/" not in parsed.path or not parsed.path.endswith("_paper.html"):
        return None
    pdf_path = parsed.path.replace("/html/", "/papers/").replace("_paper.html", "_paper.pdf")
    return f"{parsed.scheme}://{parsed.netloc}{pdf_path}"


async def _fetch_json(client: httpx.AsyncClient, url: str) -> object:
    try:
        response = await client.get(url)
    except Exception as exc:
        raise AppError(502, f"Failed to fetch CVF data from {url}: {exc}") from exc
    if response.status_code >= 400:
        raise AppError(502, f"Failed to fetch CVF data from {url}: HTTP {response.status_code}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise AppError(502, f"CVF returned invalid JSON from {url}.") from exc


async def _fetch_optional_json(client: httpx.AsyncClient, url: str) -> object | None:
    try:
        return await _fetch_json(client, url)
    except AppError as exc:
        if "HTTP 404" in exc.message:
            return None
        raise


def _paper_from_item(item: dict[str, object], abstract: str | None, source_url: str) -> CVFPaper:
    item_id = str(item.get("id") or item.get("sourceid") or "")
    paper_url = _normalize_text(item.get("paper_pdf_url")) or _normalize_text(item.get("paper_url")) or None
    virtual_url = _normalize_text(item.get("virtualsite_url")) or None
    return CVFPaper(
        id=item_id,
        title=_normalize_text(item.get("name")) or "Untitled CVF paper",
        authors=[_normalize_text(author.get("fullname")) for author in item.get("authors", []) if isinstance(author, dict) and author.get("fullname")],
        abstract=abstract,
        keywords=[_normalize_text(keyword) for keyword in item.get("keywords", []) if keyword],
        eventType=_normalize_text(item.get("event_type") or item.get("eventtype")) or None,
        session=_normalize_text(item.get("session")) or None,
        virtualUrl=urljoin(source_url, virtual_url) if virtual_url else None,
        paperUrl=paper_url,
        pdfUrl=_derive_pdf_url(paper_url),
    )


async def search_cvf(body: CVFSearchBody) -> CVFSearchData:
    raw_source_url = body.source_url
    year = _extract_year(raw_source_url)
    source_url = _source_url_from_input(raw_source_url, year)
    query = _extract_query(source_url, body.query)
    if query is None:
        query = _extract_query(raw_source_url, body.query)
    papers_url, abstracts_url = _data_urls(source_url)

    headers = {"user-agent": "ResearchAIAgentAPI/0.1 (+cvf-search)"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        papers_payload = await _fetch_json(client, papers_url)
        abstracts_payload = await _fetch_optional_json(client, abstracts_url)

    if not isinstance(papers_payload, dict) or not isinstance(papers_payload.get("results"), list):
        raise AppError(502, "CVF papers JSON did not contain a results list.")
    abstracts = abstracts_payload if isinstance(abstracts_payload, dict) else {}
    limit = min(body.limit, CVF_MAX_LIMIT)

    scored_matches: list[tuple[int, int, CVFPaper]] = []
    for index, item in enumerate(papers_payload["results"]):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        source_id = str(item.get("sourceid") or "")
        abstract = _normalize_text(abstracts.get(item_id) or abstracts.get(source_id)) or None
        score = _query_score(item, abstract, query)
        if score <= 0:
            continue
        scored_matches.append((score, index, _paper_from_item(item, abstract, source_url)))

    if query:
        scored_matches.sort(key=lambda match: (-match[0], match[1]))
    matched = [paper for _score, _index, paper in scored_matches[:limit]]

    limitations = [
        "Results come from CVF virtual conference metadata and abstracts, not necessarily full-text papers.",
        "PDF URLs are derived from CVF OpenAccess HTML links when possible.",
    ]
    if abstracts_payload is None:
        limitations.append("CVF abstracts JSON was unavailable for this year, so matching used titles, keywords, and authors only.")

    return CVFSearchData(
        conference=_conference_from_url(source_url, year),
        sourceUrl=source_url,
        query=query,
        totalResults=int(papers_payload.get("count") or len(papers_payload["results"])),
        returnedResults=len(matched),
        papers=matched,
        limitations=limitations,
    )
