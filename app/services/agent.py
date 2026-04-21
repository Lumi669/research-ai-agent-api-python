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


AGENT_TOOLS = [
    summarize_paper_tool,
    extract_paper_tool,
    read_pdf_article_tool,
    compare_pdf_articles_tool,
    analyze_conference_tool,
]


def _build_llm() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise AppError(503, "OpenAI API key is not configured (OPENAI_API_KEY)")

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
    system_prompt, _history, last_user = _extract_agent_inputs(body)
    return AgentChatData(
        reply=(
            f"Hello, mock agent mode is enabled. I am using the system prompt: {system_prompt[:120]}..."
            " I can summarize papers, analyze conference pages, and compare PDF articles once live model access is available."
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

    return AgentChatData(reply=str(final_message.content).strip(), provider="openai", toolsUsed=tools_used)
