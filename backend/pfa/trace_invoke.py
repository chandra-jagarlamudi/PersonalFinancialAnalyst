"""Optional LangSmith traces around tool execution (slice 11)."""

from __future__ import annotations

import os
from typing import Any

from pfa.agent_tools import invoke_tool as _invoke_tool_raw


def _langsmith_traceable() -> Any | None:
    """Return LangSmith ``traceable`` or ``None`` if the package is missing."""
    try:
        from langsmith import traceable
    except ImportError:
        return None
    return traceable


def invoke_tool_traced(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Delegates to ``invoke_tool``; wraps LangSmith ``traceable`` when tracing is enabled."""
    tracing_on = os.environ.get("LANGCHAIN_TRACING_V2", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not tracing_on:
        return _invoke_tool_raw(name, arguments)

    traceable = _langsmith_traceable()
    if traceable is None:
        return _invoke_tool_raw(name, arguments)

    @traceable(name=f"tool:{name}", run_type="tool")
    def _run_with_trace() -> dict[str, Any]:
        return _invoke_tool_raw(name, arguments)

    return _run_with_trace()
