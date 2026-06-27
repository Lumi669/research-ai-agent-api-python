from __future__ import annotations

import time
from contextvars import ContextVar
from types import TracebackType
from typing import Any

_trace_depth: ContextVar[int] = ContextVar("trace_depth", default=0)


def _indent(depth: int) -> str:
    return "  " * depth


class trace_call:
    def __init__(self, name: str, description: str | None = None) -> None:
        self.name = name
        self.description = description
        self.depth = 0
        self.started_at = 0.0
        self._token: Any = None

    def __enter__(self) -> "trace_call":
        self.depth = _trace_depth.get()
        suffix = f" - {self.description}" if self.description else ""
        print(f"{_indent(self.depth)}▶ {self.name}(){suffix}", flush=True)
        self.started_at = time.perf_counter()
        self._token = _trace_depth.set(self.depth + 1)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        elapsed_ms = int((time.perf_counter() - self.started_at) * 1000)
        if self._token is not None:
            _trace_depth.reset(self._token)
        status = " error" if exc_type else ""
        print(f"{_indent(self.depth)}◀ {self.name}() ({elapsed_ms} ms){status}", flush=True)


def trace_event(message: str) -> None:
    print(f"{_indent(_trace_depth.get())}• {message}", flush=True)


def result_size(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, str):
        return f"str chars={len(value)}"
    if isinstance(value, (list, tuple, set)):
        return f"{type(value).__name__} items={len(value)}"
    if isinstance(value, dict):
        return f"dict keys={len(value)}"

    articles = getattr(value, "articles", None)
    if isinstance(articles, list):
        return f"{type(value).__name__} articles={len(articles)}"

    papers = getattr(value, "papers", None)
    if isinstance(papers, list):
        return f"{type(value).__name__} papers={len(papers)}"

    text = getattr(value, "text", None)
    if isinstance(text, str):
        return f"{type(value).__name__} text_chars={len(text)}"

    return type(value).__name__
