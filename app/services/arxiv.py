import asyncio
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, unquote_plus, urlparse

import httpx

from app.core.errors import AppError
from app.models.arxiv import ArxivArticle, ArxivSearchBody, ArxivSearchData

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_ABS_URL = "https://arxiv.org/abs/{arxiv_id}"
ARXIV_MAX_LIMIT = 25
ARXIV_RETRYABLE_STATUS_CODES = {429, 503}
ARXIV_RETRY_DELAYS_SECONDS = (1.0, 2.0)
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "opensearch": "http://a9.com/-/spec/opensearch/1.1/"}


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _query_from_input(value: str) -> str:
    stripped = value.strip()
    embedded_url = re.search(r"https?://arxiv\.org/[^\s,;]+", stripped)
    parsed = urlparse(embedded_url.group(0) if embedded_url else stripped)
    if parsed.netloc.endswith("arxiv.org"):
        params = parse_qs(parsed.query)
        query = params.get("query", [""])[0] or params.get("search_query", [""])[0]
        if query:
            return unquote_plus(query).strip()
        if parsed.path.startswith("/abs/"):
            return f"id:{parsed.path.removeprefix('/abs/').strip()}"
    return stripped


def _api_query(query: str) -> str:
    if query.startswith("id:") or query.startswith("all:") or query.startswith("cat:") or query.startswith("au:") or query.startswith("ti:"):
        return query
    return f"all:{query}"


def _entry_text(entry: ET.Element, tag: str) -> str | None:
    node = entry.find(f"atom:{tag}", ATOM_NS)
    return _normalize_text(node.text if node is not None else None) or None


def _arxiv_id_from_entry_id(entry_id: str) -> str:
    parsed = urlparse(entry_id)
    return parsed.path.removeprefix("/abs/").strip() or entry_id.rstrip("/").rsplit("/", 1)[-1]


def _parse_arxiv_feed(xml_text: str) -> tuple[int | None, list[ArxivArticle]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise AppError(502, "arXiv returned invalid XML.") from exc

    total_text = root.findtext("opensearch:totalResults", namespaces=ATOM_NS)
    total_results = int(total_text) if total_text and total_text.isdigit() else None
    articles: list[ArxivArticle] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = _entry_text(entry, "id")
        title = _entry_text(entry, "title")
        abstract = _entry_text(entry, "summary")
        if not entry_id or not title or not abstract:
            continue

        arxiv_id = _arxiv_id_from_entry_id(entry_id)
        authors = [_normalize_text(author.findtext("atom:name", namespaces=ATOM_NS)) for author in entry.findall("atom:author", ATOM_NS)]
        categories = [category.attrib.get("term", "") for category in entry.findall("atom:category", ATOM_NS)]
        pdf_url: str | None = None
        for link in entry.findall("atom:link", ATOM_NS):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href")
                break

        articles.append(
            ArxivArticle(
                arxivId=arxiv_id,
                title=title,
                authors=[author for author in authors if author],
                abstract=abstract,
                published=_entry_text(entry, "published"),
                updated=_entry_text(entry, "updated"),
                categories=[category for category in categories if category],
                url=ARXIV_ABS_URL.format(arxiv_id=arxiv_id),
                pdfUrl=pdf_url,
                doi=_entry_text(entry, "doi"),
            )
        )

    return total_results, articles


async def search_arxiv(body: ArxivSearchBody) -> ArxivSearchData:
    query = _query_from_input(body.query)
    limit = min(body.limit, ARXIV_MAX_LIMIT)
    headers = {"user-agent": "ResearchAIAgentAPI/0.1 (+arxiv-search)"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        for attempt in range(len(ARXIV_RETRY_DELAYS_SECONDS) + 1):
            try:
                response = await client.get(
                    ARXIV_API_URL,
                    params={
                        "search_query": _api_query(query),
                        "start": 0,
                        "max_results": limit,
                        "sortBy": body.sort_by,
                        "sortOrder": body.sort_order,
                    },
                )
            except Exception as exc:
                raise AppError(502, f"Failed to search arXiv: {exc}") from exc

            if response.status_code not in ARXIV_RETRYABLE_STATUS_CODES:
                break
            if attempt >= len(ARXIV_RETRY_DELAYS_SECONDS):
                raise AppError(response.status_code, f"arXiv is temporarily unavailable: HTTP {response.status_code}")
            await asyncio.sleep(ARXIV_RETRY_DELAYS_SECONDS[attempt])

    if response.status_code >= 400:
        raise AppError(502, f"Failed to search arXiv: HTTP {response.status_code}")

    total_results, articles = _parse_arxiv_feed(response.text)
    return ArxivSearchData(
        query=query,
        totalResults=total_results,
        returnedResults=len(articles),
        articles=articles,
        limitations=[
            "Results come from arXiv metadata and abstracts, not full-text PDFs.",
            "The arXiv API search ordering may differ slightly from the browser search page.",
        ],
    )
