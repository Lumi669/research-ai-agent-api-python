import json
from typing import Any

from openai import APIError

from app.core.config import settings
from app.core.errors import AppError
from app.models.agent import AgentChatBody, AgentChatData
from app.models.conferences import AnalyzeConferenceBody
from app.models.papers import ComparePdfArticlesBody, ExtractPaperBody, ReadPdfArticleBody, SummarizePaperBody
from app.services.conference import analyze_conference
from app.services.openai_client import get_openai_client
from app.services.papers import compare_pdf_articles, extract_paper, summarize_paper
from app.services.pdf_reader import read_pdf_article
from app.services.usage import get_usage_summary, list_usage_events


async def _run_mock_agent(body: AgentChatBody) -> AgentChatData:
    last_user = next((message.content for message in reversed(body.messages) if message.role == "user"), None)
    if not last_user:
        raise AppError(400, "At least one user message is required.")
    if any(token in last_user.lower() for token in ["usage", "cost", "spend", "token"]):
        summary = get_usage_summary()
        return AgentChatData(reply=f"Mock agent summary: {summary.total_events} tracked events, {summary.total_tokens} total tokens, estimated cost ${summary.total_estimated_cost_usd:.6f}.", provider="mock", toolsUsed=["get_usage_summary"])
    return AgentChatData(reply="Hello, Mock agent mode is enabled. I can summarize papers, analyze conference pages, compare PDF articles, and report usage once live model access is available.", provider="mock", toolsUsed=[])


async def chat_with_agent(body: AgentChatBody) -> AgentChatData:
    if settings.mock_openai:
        return await _run_mock_agent(body)

    if settings.agent_provider.strip().lower() == "bedrock":
        raise AppError(501, "AGENT_PROVIDER=bedrock is not implemented yet.")

    client = get_openai_client()
    messages: list[dict[str, Any]] = [{"role": msg.role, "content": msg.content} for msg in body.messages]
    tools_used: list[str] = []

    tools = [
        {
            "type": "function",
            "function": {
                "name": "summarize_paper",
                "description": "Summarize a single academic paper or excerpt into structured research notes.",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "text": {"type": "string"}, "mode": {"type": "string", "enum": ["short", "standard"]}}, "required": ["text"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_paper",
                "description": "Extract keywords, datasets, metrics, and limitations from a paper excerpt.",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "text": {"type": "string"}}, "required": ["text"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_pdf_article",
                "description": "Fetch a PDF article by URL and extract readable text plus basic metadata.",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "pdfUrl": {"type": "string"}, "maxChars": {"type": "integer"}}, "required": ["pdfUrl"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_pdf_articles",
                "description": "Read two PDF articles and compare them for similarities and differences.",
                "parameters": {"type": "object", "properties": {"left": {"type": "object"}, "right": {"type": "object"}, "focus": {"type": "string"}, "mode": {"type": "string", "enum": ["short", "standard"]}, "maxCharsPerPaper": {"type": "integer"}}, "required": ["left", "right"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_conference",
                "description": "Fetch a conference accepted-papers page and synthesize cross-paper findings.",
                "parameters": {"type": "object", "properties": {"conference": {"type": "string"}, "sourceUrl": {"type": "string"}, "mode": {"type": "string", "enum": ["short", "standard"]}, "maxPapers": {"type": "integer"}, "maxPaperChars": {"type": "integer"}}, "required": ["conference", "sourceUrl"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_usage_summary",
                "description": "Return aggregate token usage and estimated cost summary for the API.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_usage_events",
                "description": "Return recent usage events.",
                "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            },
        },
    ]

    for _ in range(4):
        try:
            completion = client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.1,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except APIError as exc:
            raise AppError(502, f"OpenAI request failed ({exc.status_code or 'error'}): {exc.message}") from exc

        assistant = completion.choices[0].message
        if not assistant.tool_calls:
            content = assistant.content or ""
            if not content:
                raise AppError(502, "The agent returned an empty reply.")
            return AgentChatData(reply=content, provider="openai", toolsUsed=tools_used)

        messages.append({"role": "assistant", "content": assistant.content or "", "tool_calls": [tool.model_dump() for tool in assistant.tool_calls]})
        for tool_call in assistant.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")
            tools_used.append(name)
            if name == "summarize_paper":
                result = await summarize_paper(SummarizePaperBody(**args))
            elif name == "extract_paper":
                result = await extract_paper(ExtractPaperBody(**args))
            elif name == "read_pdf_article":
                result = await read_pdf_article(str(args["pdfUrl"]), args.get("title"), int(args.get("maxChars", 20000)))
            elif name == "compare_pdf_articles":
                result = await compare_pdf_articles(ComparePdfArticlesBody(**args))
            elif name == "analyze_conference":
                result = await analyze_conference(AnalyzeConferenceBody(**args))
            elif name == "get_usage_summary":
                result = get_usage_summary()
            elif name == "list_usage_events":
                result = list_usage_events(int(args.get("limit", 20)))
            else:
                result = {"error": f"Unsupported tool: {name}"}

            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result.model_dump(mode="json") if hasattr(result, "model_dump") else result, default=str)})

    raise AppError(502, "The agent exceeded the maximum tool-call loop limit.")
