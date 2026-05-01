"""LangSmith tracing shim for tool invokes (slice 11)."""

from __future__ import annotations

import os

import pytest

from pfa.trace_invoke import invoke_tool_traced


def test_invoke_tool_traced_unknown_tool_without_tracing_env():
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    with pytest.raises(ValueError, match="unknown tool"):
        invoke_tool_traced("not_a_real_tool", {})
