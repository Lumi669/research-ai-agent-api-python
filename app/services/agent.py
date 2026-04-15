from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.errors import AppError
from app.models.agent import AgentChatBody, AgentChatData
from app.models.conferences import AnalyzeConferenceBody
from app.models.papers import ComparePdfArticlesBody, ExtractPaperBody, SummarizePaperBody
from app.services.conference import analyze_conference
from app.services.papers import compare_pdf_articles, extract_paper, summarize_paper
from app.services.pdf_reader import read_pdf_article
from app.services.usage import get_usage_summary, list_usage_events

DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are a research AI agent. Hold a helpful conversation, decide when to use tools, "
    "and ground your answers in tool results whenever the user needs paper analysis, PDF "
    "reading, conference analysis, or usage data."
)


@tool
async def summarize_paper_tool(text: str, title: str | None = None, mode: str = "standard") -> dict[str, Any]:
    """Summarize one academic paper or excerpt into structured research notes."""

    result = await summarize_paper(SummarizePaperBody(title=title, text=text, mode=mode))
    return result.model_dump(mode="json", by_alias=True)


@tool
async def extract_paper_tool(text: str, title: str | None = None) -> dict[str, Any]:
    """Extract keywords, datasets, metrics, and limitations from a paper excerpt."""

    result = await extract_paper(ExtractPaperBody(title=title, text=text))
    return result.model_dump(mode="json", by_alias=True)


@tool
async def read_pdf_article_tool(pdf_url: str, title: str | None = None, max_chars: int = 20_000) -> dict[str, Any]:
    """Fetch a PDF article by URL and extract readable text plus metadata."""

    result = await read_pdf_article(pdf_url=pdf_url, title=title, max_chars=max_chars)
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

    result = await compare_pdf_articles(
        ComparePdfArticlesBody(
            left={"title": left_title, "pdfUrl": left_pdf_url},
            right={"title": right_title, "pdfUrl": right_pdf_url},
            focus=focus,
            mode=mode,
            maxCharsPerPaper=max_chars_per_paper,
        )
    )
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

    result = await analyze_conference(
        AnalyzeConferenceBody(
            conference=conference,
            sourceUrl=source_url,
            mode=mode,
            maxPapers=max_papers,
            maxPaperChars=max_paper_chars,
        )
    )
    return result.model_dump(mode="json", by_alias=True)


@tool
def get_usage_summary_tool() -> dict[str, Any]:
    """Return aggregate token usage and estimated cost summary for the API."""

    result = get_usage_summary()
    return result.model_dump(mode="json", by_alias=True)


@tool
def list_usage_events_tool(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent usage events."""

    return [event.model_dump(mode="json", by_alias=True) for event in list_usage_events(limit)]


AGENT_TOOLS = [
    summarize_paper_tool,
    extract_paper_tool,
    read_pdf_article_tool,
    compare_pdf_articles_tool,
    analyze_conference_tool,
    get_usage_summary_tool,
    list_usage_events_tool,
]


def _build_llm() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise AppError(503, "OpenAI API key is not configured (OPENAI_API_KEY)")

    return ChatOpenAI(model=settings.openai_model, temperature=0.1, api_key=settings.openai_api_key)


def _extract_agent_inputs(body: AgentChatBody) -> tuple[str, list[BaseMessage], str]:
    system_messages = [message.content.strip() for message in body.messages if message.role == "system" and message.content.strip()]
    conversation: list[BaseMessage] = []
    last_user_message: str | None = None

    for message in body.messages:
        if message.role == "system":
            continue
        if message.role == "user":
            conversation.append(HumanMessage(content=message.content))
            last_user_message = message.content
        elif message.role == "assistant":
            conversation.append(AIMessage(content=message.content))

    if last_user_message is None:
        raise AppError(400, "At least one user message is required.")

    system_prompt = "\n\n".join(system_messages) if system_messages else DEFAULT_AGENT_SYSTEM_PROMPT
    return system_prompt, conversation, last_user_message


async def _run_mock_agent(body: AgentChatBody) -> AgentChatData:
    system_prompt, _history, last_user = _extract_agent_inputs(body)
    if any(token in last_user.lower() for token in ["usage", "cost", "spend", "token"]):
        summary = get_usage_summary()
        return AgentChatData(
            reply=(
                f"Mock agent summary: {summary.total_events} tracked events, "
                f"{summary.total_tokens} total tokens, estimated cost "
                f"${summary.total_estimated_cost_usd:.6f}."
            ),
            provider="mock",
            toolsUsed=["get_usage_summary_tool"],
        )
    return AgentChatData(
        reply=(
            f"Hello, mock agent mode is enabled. I am using the system prompt: {system_prompt[:120]}..."
            " I can summarize papers, analyze conference pages, compare PDF articles, and report usage once live model access is available."
        ),
        provider="mock",
        toolsUsed=[],
    )


async def chat_with_agent(body: AgentChatBody) -> AgentChatData:
    if settings.mock_openai:
        return await _run_mock_agent(body)

    if settings.agent_provider.strip().lower() == "bedrock":
        raise AppError(501, "AGENT_PROVIDER=bedrock is not implemented yet.")

    system_prompt, conversation, _last_user = _extract_agent_inputs(body)
    agent = create_agent(model=_build_llm(), tools=AGENT_TOOLS, system_prompt=system_prompt)

    try:
        result = await agent.ainvoke({"messages": conversation})
    except AppError:
        raise
    except Exception as exc:
        raise AppError(502, f"Agent execution failed: {exc}") from exc

    result_messages = result.get("messages", [])
    final_message = next((message for message in reversed(result_messages) if isinstance(message, AIMessage) and message.content), None)
    if not final_message:
        raise AppError(502, "The agent returned an empty reply.")

    tools_used: list[str] = []
    for message in result_messages:
        if isinstance(message, AIMessage):
            for tool_call in getattr(message, "tool_calls", []):
                tool_name = tool_call.get("name")
                if tool_name:
                    tools_used.append(tool_name)

    return AgentChatData(reply=str(final_message.content).strip(), provider="openai", toolsUsed=tools_used)
