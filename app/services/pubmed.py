import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, unquote_plus, urlparse

import httpx

from app.core.errors import AppError
from app.models.pubmed import PubMedArticle, PubMedSearchBody, PubMedSearchData

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_ARTICLE_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
PUBMED_MAX_LIMIT = 25
PUBMED_CACHE_TTL_SECONDS = 600
PUBMED_RETRY_DELAYS_SECONDS = (1.0, 2.0)
_pubmed_search_cache: dict[tuple[str, int, str], tuple[float, PubMedSearchData]] = {}


def _get_cached_pubmed_search(key: tuple[str, int, str]) -> PubMedSearchData | None:
    cached = _pubmed_search_cache.get(key)
    if not cached:
        return None
    cached_at, data = cached
    if time.monotonic() - cached_at > PUBMED_CACHE_TTL_SECONDS:
        _pubmed_search_cache.pop(key, None)
        return None
    return data.model_copy(deep=True)


def _cache_pubmed_search(key: tuple[str, int, str], data: PubMedSearchData) -> PubMedSearchData:
    _pubmed_search_cache[key] = (time.monotonic(), data.model_copy(deep=True))
    return data


def _query_from_input(value: str) -> str:
    stripped = value.strip()
    embedded_url = re.search(r"https?://pubmed\.ncbi\.nlm\.nih\.gov/[^\s,;]+", stripped)
    parsed = urlparse(embedded_url.group(0) if embedded_url else stripped)
    if parsed.netloc.endswith("pubmed.ncbi.nlm.nih.gov"):
        query = parse_qs(parsed.query).get("term", [""])[0]
        return unquote_plus(query).strip() or stripped
    return stripped


def _text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    value = "".join(node.itertext())
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def _article_pub_date(article: ET.Element) -> str | None:
    pub_date = article.find(".//JournalIssue/PubDate")
    if pub_date is None:
        return None
    year = pub_date.findtext("Year")
    month = pub_date.findtext("Month")
    day = pub_date.findtext("Day")
    medline_date = pub_date.findtext("MedlineDate")
    if year:
        parts = [year]
        if month:
            parts.append(month)
        if day:
            parts.append(day)
        return " ".join(parts)
    return medline_date


def _article_authors(article: ET.Element) -> list[str]:
    authors: list[str] = []
    for author in article.findall(".//AuthorList/Author"):
        collective = author.findtext("CollectiveName")
        if collective:
            authors.append(collective)
            continue
        last = author.findtext("LastName")
        initials = author.findtext("Initials")
        if last and initials:
            authors.append(f"{last} {initials}")
        elif last:
            authors.append(last)
    return authors


def _article_abstract(article: ET.Element) -> str | None:
    fragments: list[str] = []
    for abstract_text in article.findall(".//Abstract/AbstractText"):
        text = _text(abstract_text)
        if not text:
            continue
        label = abstract_text.attrib.get("Label")
        fragments.append(f"{label}: {text}" if label else text)
    return " ".join(fragments) or None


def _article_doi(article: ET.Element) -> str | None:
    for article_id in article.findall(".//ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType") == "doi" and article_id.text:
            return article_id.text.strip()
    return None


def _parse_pubmed_articles(xml_text: str) -> list[PubMedArticle]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise AppError(502, "PubMed returned invalid XML.") from exc

    articles: list[PubMedArticle] = []
    for item in root.findall("PubmedArticle"):
        pmid = item.findtext(".//MedlineCitation/PMID")
        title_node = item.find(".//ArticleTitle")
        if not pmid or title_node is None:
            continue
        publication_types = [_text(node) for node in item.findall(".//PublicationTypeList/PublicationType")]
        articles.append(
            PubMedArticle(
                pmid=pmid,
                title=_text(title_node) or "Untitled PubMed article",
                journal=item.findtext(".//Journal/Title"),
                pubDate=_article_pub_date(item),
                authors=_article_authors(item),
                publicationTypes=[value for value in publication_types if value],
                abstract=_article_abstract(item),
                url=PUBMED_ARTICLE_URL.format(pmid=pmid),
                doi=_article_doi(item),
            )
        )
    return articles


async def search_pubmed(body: PubMedSearchBody) -> PubMedSearchData:
    query = _query_from_input(body.query)
    limit = min(body.limit, PUBMED_MAX_LIMIT)
    cache_key = (query.lower(), limit, body.sort.lower())
    cached = _get_cached_pubmed_search(cache_key)
    if cached:
        cached.limitations.append("Returned from the local PubMed cache to avoid repeating the same remote request.")
        return cached

    headers = {"user-agent": "ResearchAIAgentAPI/0.1 (+pubmed-search)"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        for attempt in range(len(PUBMED_RETRY_DELAYS_SECONDS) + 1):
            try:
                search_response = await client.get(
                    PUBMED_ESEARCH_URL,
                    params={"db": "pubmed", "term": query, "retmode": "json", "retmax": limit, "sort": body.sort},
                )
            except Exception as exc:
                raise AppError(502, f"Failed to search PubMed: {exc}") from exc

            if search_response.status_code != 429:
                break
            if attempt >= len(PUBMED_RETRY_DELAYS_SECONDS):
                raise AppError(429, "PubMed is rate limiting requests. Please wait a moment and try again.")
            await asyncio.sleep(PUBMED_RETRY_DELAYS_SECONDS[attempt])

        if search_response.status_code >= 400:
            raise AppError(502, f"Failed to search PubMed: HTTP {search_response.status_code}")

        try:
            search_payload = search_response.json()
        except json.JSONDecodeError as exc:
            raise AppError(502, "PubMed returned invalid search JSON.") from exc

        result = search_payload.get("esearchresult", {})
        ids = [str(value) for value in result.get("idlist", [])]
        total_results = int(result.get("count") or 0)
        if not ids:
            return _cache_pubmed_search(
                cache_key,
                PubMedSearchData(
                    query=query,
                    totalResults=total_results,
                    returnedResults=0,
                    articles=[],
                    limitations=["No PubMed records were returned for this query."],
                ),
            )

        try:
            fetch_response = await client.get(
                PUBMED_EFETCH_URL,
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            )
        except Exception as exc:
            raise AppError(502, f"Failed to fetch PubMed records: {exc}") from exc

        if fetch_response.status_code >= 400:
            if fetch_response.status_code == 429:
                raise AppError(429, "PubMed is rate limiting record fetch requests. Please wait a moment and try again.")
            raise AppError(502, f"Failed to fetch PubMed records: HTTP {fetch_response.status_code}")

    articles = _parse_pubmed_articles(fetch_response.text)
    limitations = [
        "Results come from PubMed metadata and abstracts, not full-text articles.",
        "The first results may include reviews, editorials, or records without abstracts.",
    ]
    return _cache_pubmed_search(
        cache_key,
        PubMedSearchData(
            query=query,
            totalResults=total_results,
            returnedResults=len(articles),
            articles=articles,
            limitations=limitations,
        ),
    )
