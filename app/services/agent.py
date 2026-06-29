import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.errors import AppError
from app.core.trace import result_size, trace_call, trace_event
from app.models.agent import AgentChatBody, AgentChatData
from app.models.arxiv import ArxivSearchBody
from app.models.conferences import AnalyzeConferenceBody
from app.models.cvf import CVFSearchBody
from app.models.papers import ComparePdfArticlesBody, ExtractPaperBody, SummarizePaperBody
from app.models.pubmed import PubMedSearchBody
from app.services.conference import analyze_conference
from app.services.arxiv import search_arxiv
from app.services.cvf import search_cvf
from app.services.papers import compare_pdf_articles, extract_paper, summarize_paper
from app.services.pdf_reader import read_pdf_article
from app.services.pubmed import search_pubmed

AgentProgressCallback = Callable[[str], None]
_agent_progress_callback: ContextVar[AgentProgressCallback | None] = ContextVar("agent_progress_callback", default=None)


@contextmanager
def agent_progress(callback: AgentProgressCallback | None):
    token = _agent_progress_callback.set(callback)
    try:
        yield
    finally:
        _agent_progress_callback.reset(token)


def _emit_agent_progress(message: str) -> None:
    callback = _agent_progress_callback.get()
    if callback:
        callback(message)


def _extract_requested_limit(text: str, default: int = 10) -> int:
    match = re.search(r"\bfirst\s+(\d{1,2})\b|\btop\s+(\d{1,2})\b|\blatest\s+(\d{1,2})\b", text, flags=re.IGNORECASE)
    if not match:
        return default
    return max(1, min(25, int(next(value for value in match.groups() if value))))


def _format_pubmed_mock_reply(data: dict[str, Any]) -> str:
    articles = data.get("articles", [])
    lines = [
        f"Mock mode PubMed summary for query: {data.get('query')}",
        f"Returned {data.get('returnedResults')} of {data.get('totalResults')} PubMed results.",
        "",
    ]
    for index, article in enumerate(articles, start=1):
        abstract = article.get("abstract") or "No abstract available."
        summary = abstract[:240].rstrip() + ("..." if len(abstract) > 240 else "")
        lines.append(f"{index}. {article.get('title')} ({article.get('pubDate') or 'date unknown'}, PMID {article.get('pmid')})")
        lines.append(f"   {summary}")
    lines.extend(
        [
            "",
            "Limitations: this mock-mode response uses PubMed metadata and abstract snippets only, not full-text papers or OpenAI reasoning.",
        ]
    )
    return "\n".join(lines)


def _format_arxiv_mock_reply(data: dict[str, Any]) -> str:
    articles = data.get("articles", [])
    lines = [
        f"Mock mode arXiv summary for query: {data.get('query')}",
        f"Returned {data.get('returnedResults')} of {data.get('totalResults')} arXiv results.",
        "",
    ]
    for index, article in enumerate(articles, start=1):
        abstract = article.get("abstract") or "No abstract available."
        summary = abstract[:240].rstrip() + ("..." if len(abstract) > 240 else "")
        lines.append(f"{index}. {article.get('title')} ({article.get('published') or 'date unknown'}, {article.get('arxivId')})")
        lines.append(f"   {summary}")
    lines.extend(
        [
            "",
            "Limitations: this mock-mode response uses arXiv metadata and abstract snippets only, not full-text PDFs or OpenAI reasoning.",
        ]
    )
    return "\n".join(lines)


def _format_cvf_mock_reply(data: dict[str, Any]) -> str:
    papers = data.get("papers", [])
    lines = [
        f"Mock mode {data.get('conference') or 'CVF'} summary for: {data.get('sourceUrl')}",
        f"Returned {data.get('returnedResults')} of {data.get('totalResults')} papers.",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        abstract = paper.get("abstract") or "No abstract available."
        summary = abstract[:240].rstrip() + ("..." if len(abstract) > 240 else "")
        lines.append(f"{index}. {paper.get('title')} ({paper.get('eventType') or 'event type unknown'}, {paper.get('id')})")
        lines.append(f"   {summary}")
    lines.extend(
        [
            "",
            "Limitations: this mock-mode response uses CVF metadata and abstract snippets only, not full OpenAccess paper text or OpenAI reasoning.",
        ]
    )
    return "\n".join(lines)


def _extract_message_token_usage(message: BaseMessage) -> tuple[int, int]:
    usage_metadata = getattr(message, "usage_metadata", None) or {}
    if isinstance(usage_metadata, dict):
        prompt_tokens = int(usage_metadata.get("input_tokens") or 0)
        completion_tokens = int(usage_metadata.get("output_tokens") or 0)
        if prompt_tokens or completion_tokens:
            return prompt_tokens, completion_tokens

    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
    if isinstance(token_usage, dict):
        return int(token_usage.get("prompt_tokens") or 0), int(token_usage.get("completion_tokens") or 0)

    return 0, 0


@tool
async def summarize_paper_tool(text: str, title: str | None = None, mode: str = "standard") -> dict[str, Any]:
    """Summarize one academic paper or excerpt into structured research notes."""

    with trace_call("summarize_paper_tool", "LangChain tool: summarize one paper"):
        trace_event("tool=summarize_paper_tool")
        result = await summarize_paper(SummarizePaperBody(title=title, text=text, mode=mode))
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def extract_paper_tool(text: str, title: str | None = None) -> dict[str, Any]:
    """Extract keywords, datasets, metrics, and limitations from a paper excerpt."""

    with trace_call("extract_paper_tool", "LangChain tool: extract paper metadata"):
        trace_event("tool=extract_paper_tool")
        result = await extract_paper(ExtractPaperBody(title=title, text=text))
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def read_pdf_article_tool(pdf_url: str, title: str | None = None, max_chars: int = 20_000) -> dict[str, Any]:
    """Fetch a PDF article by URL and extract readable text plus metadata."""

    with trace_call("read_pdf_article_tool", "LangChain tool: read PDF article"):
        trace_event("tool=read_pdf_article_tool")
        _emit_agent_progress("Reading document for more detail...")
        result = await read_pdf_article(pdf_url=pdf_url, title=title, max_chars=max_chars)
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def compare_pdf_articles_tool(
    left_pdf_url: str,
    right_pdf_url: str,
    left_title: str | None = None,
    right_title: str | None = None,
    focus: str | None = None,
    mode: str = "standard",
    max_chars_per_paper: int = 12_000,
) -> dict[str, Any]:
    """Read two PDF articles and compare them for similarities and differences."""

    with trace_call("compare_pdf_articles_tool", "LangChain tool: compare two PDF articles"):
        trace_event("tool=compare_pdf_articles_tool")
        result = await compare_pdf_articles(
            ComparePdfArticlesBody(
                left={"title": left_title, "pdfUrl": left_pdf_url},
                right={"title": right_title, "pdfUrl": right_pdf_url},
                focus=focus,
                mode=mode,
                maxCharsPerPaper=max_chars_per_paper,
            )
        )
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def analyze_conference_tool(
    conference: str,
    source_url: str,
    mode: str = "standard",
    max_papers: int = 8,
    max_paper_chars: int = 2500,
) -> dict[str, Any]:
    """Fetch a conference accepted-papers page and synthesize cross-paper findings."""

    with trace_call("analyze_conference_tool", "LangChain tool: analyze conference page"):
        trace_event("tool=analyze_conference_tool")
        result = await analyze_conference(
            AnalyzeConferenceBody(
                conference=conference,
                sourceUrl=source_url,
                mode=mode,
                maxPapers=max_papers,
                maxPaperChars=max_paper_chars,
            )
        )
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def search_pubmed_tool(query_or_url: str, limit: int = 10, sort: str = "relevance") -> dict[str, Any]:
    """Search PubMed or read a PubMed search URL, returning article metadata and abstracts. For follow-up comparisons of papers already listed, use conversation context if enough; if not enough, call this tool to retrieve more detail before comparing."""

    with trace_call("search_pubmed_tool", "LangChain tool: search PubMed"):
        trace_event("tool=search_pubmed_tool")
        _emit_agent_progress("Current context may be limited; retrieving PubMed details...")
        try:
            result = await search_pubmed(PubMedSearchBody(query=query_or_url, limit=limit, sort=sort))
        except AppError as exc:
            if exc.status_code != 429:
                raise
            fallback = {
                "query": query_or_url,
                "totalResults": 0,
                "returnedResults": 0,
                "articles": [],
                "limitations": [
                    "PubMed is temporarily rate limiting requests.",
                    "For follow-up questions, answer from the papers already present in the conversation when possible.",
                ],
                "error": exc.message,
            }
            trace_event(f"tool result: {result_size(fallback)}")
            return fallback
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def search_arxiv_tool(
    query_or_url: str,
    limit: int = 10,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
) -> dict[str, Any]:
    """Search arXiv or read an arXiv search URL, returning article metadata, abstracts, and PDF links."""

    with trace_call("search_arxiv_tool", "LangChain tool: search arXiv"):
        trace_event("tool=search_arxiv_tool")
        _emit_agent_progress("Current context may be limited; retrieving arXiv details...")
        result = await search_arxiv(ArxivSearchBody(query=query_or_url, limit=limit, sortBy=sort_by, sortOrder=sort_order))
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


@tool
async def search_cvf_tool(source_url: str, query: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Search a CVF/CVPR virtual papers page, returning paper metadata, abstracts, and derived OpenAccess PDF links."""

    with trace_call("search_cvf_tool", "LangChain tool: search CVF/CVPR"):
        trace_event("tool=search_cvf_tool")
        _emit_agent_progress("Current context may be limited; retrieving CVF details...")
        result = await search_cvf(CVFSearchBody(sourceUrl=source_url, query=query, limit=limit))
        trace_event(f"tool result: {result_size(result)}")
        return result.model_dump(mode="json", by_alias=True)


AGENT_TOOLS = [
    summarize_paper_tool,
    extract_paper_tool,
    read_pdf_article_tool,
    compare_pdf_articles_tool,
    analyze_conference_tool,
    search_pubmed_tool,
    search_arxiv_tool,
    search_cvf_tool,
]


def _build_llm() -> ChatOpenAI:
    with trace_call("_build_llm", "Configure ChatOpenAI client"):
        if not settings.openai_api_key:
            raise AppError(503, "OpenAI API key is not configured (OPENAI_API_KEY)")

        trace_event(f"model={settings.openai_model}")
        return ChatOpenAI(model=settings.openai_model, temperature=0.1, api_key=settings.openai_api_key)


def _extract_agent_inputs(body: AgentChatBody) -> tuple[str, list[BaseMessage], str]:
    system_messages = [message.text_content.strip() for message in body.messages if message.role == "system" and message.text_content.strip()]
    conversation: list[BaseMessage] = []
    last_user_message: str | None = None

    for message in body.messages:
        if message.role == "system":
            continue
        if message.role == "user":
            conversation.append(HumanMessage(content=message.text_content))
            last_user_message = message.text_content
        elif message.role == "assistant":
            conversation.append(AIMessage(content=message.text_content))

    if last_user_message is None:
        raise AppError(400, "At least one user message is required.")

    system_prompt = "\n\n".join(system_messages) if system_messages else settings.agent_system_prompt
    return system_prompt, conversation, last_user_message


async def _run_mock_agent(body: AgentChatBody) -> AgentChatData:
    with trace_call("_run_mock_agent", "Run local mock agent"):
        system_prompt, _history, last_user = _extract_agent_inputs(body)
        if "pubmed" in last_user.lower():
            trace_event("tool=search_pubmed_mock")
            result = await search_pubmed(PubMedSearchBody(query=last_user, limit=_extract_requested_limit(last_user)))
            trace_event(f"tool result: {result_size(result)}")
            return AgentChatData(
                reply=_format_pubmed_mock_reply(result.model_dump(mode="json", by_alias=True)),
                provider="mock",
                toolsUsed=["search_pubmed_tool"],
            )
        if "arxiv" in last_user.lower():
            trace_event("tool=search_arxiv_mock")
            result = await search_arxiv(ArxivSearchBody(query=last_user, limit=_extract_requested_limit(last_user)))
            trace_event(f"tool result: {result_size(result)}")
            return AgentChatData(
                reply=_format_arxiv_mock_reply(result.model_dump(mode="json", by_alias=True)),
                provider="mock",
                toolsUsed=["search_arxiv_tool"],
            )
        if "thecvf.com" in last_user.lower() or "cvpr" in last_user.lower():
            trace_event("tool=search_cvf_mock")
            source_url_match = re.search(r"https?://[^\s,;]+", last_user)
            source_url = source_url_match.group(0) if source_url_match else last_user
            result = await search_cvf(CVFSearchBody(sourceUrl=source_url, limit=_extract_requested_limit(last_user)))
            trace_event(f"tool result: {result_size(result)}")
            return AgentChatData(
                reply=_format_cvf_mock_reply(result.model_dump(mode="json", by_alias=True)),
                provider="mock",
                toolsUsed=["search_cvf_tool"],
            )

        return AgentChatData(
            reply=(
                f"Hello, mock agent mode is enabled. I am using the system prompt: {system_prompt[:120]}..."
                " I can summarize papers, analyze conference pages, and compare PDF articles once live model access is available."
            ),
            provider="mock",
            toolsUsed=[],
        )


async def chat_with_agent(body: AgentChatBody) -> AgentChatData:
    with trace_call("chat_with_agent", "Build and run the LangChain agent"):
        if settings.mock_openai:
            return await _run_mock_agent(body)

        if settings.agent_provider.strip().lower() == "bedrock":
            raise AppError(501, "AGENT_PROVIDER=bedrock is not implemented yet.")

        system_prompt, conversation, _last_user = _extract_agent_inputs(body)
        trace_event(f"agent input messages={len(conversation)} tools_available={len(AGENT_TOOLS)}")
        agent = create_agent(model=_build_llm(), tools=AGENT_TOOLS, system_prompt=system_prompt)

        try:
            with trace_call("LangChainAgent.ainvoke", "Send request to LLM and run selected tools"):
                trace_event("LLM request sent")
                result = await agent.ainvoke({"messages": conversation})
                trace_event("LLM response received")
        except AppError:
            raise
        except Exception as exc:
            raise AppError(502, f"Agent execution failed: {exc}") from exc

        result_messages = result.get("messages", [])
        final_message = next((message for message in reversed(result_messages) if isinstance(message, AIMessage) and message.content), None)
        if not final_message:
            raise AppError(502, "The agent returned an empty reply.")

        tools_used: list[str] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        for message in result_messages:
            prompt_tokens, completion_tokens = _extract_message_token_usage(message)
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            if isinstance(message, AIMessage):
                for tool_call in getattr(message, "tool_calls", []):
                    tool_name = tool_call.get("name")
                    if tool_name:
                        tools_used.append(tool_name)

        trace_event(f"agent output messages={len(result_messages)} tools_used={tools_used}")
        trace_event(f"token usage: prompt={total_prompt_tokens} completion={total_completion_tokens}")
        return AgentChatData(reply=str(final_message.content).strip(), provider="openai", toolsUsed=tools_used)
