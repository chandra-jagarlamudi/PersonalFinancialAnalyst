"""LangSmith tracing shim for tool invokes (slice 11)."""

from __future__ import annotations

import pytest

from pfa.trace_invoke import invoke_tool_traced


def _passthrough_traceable(*_args, **_kwargs):
    """No-op decorator so tests exercise the tracing-enabled branch without LangSmith I/O."""

    def _decorator(fn):
        return fn

    return _decorator


def test_invoke_tool_traced_unknown_tool_without_tracing_env():
    with pytest.raises(ValueError, match="unknown tool"):
        invoke_tool_traced("not_a_real_tool", {})


def test_tracing_enabled_delegates_returns_and_exceptions(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setattr(
        "pfa.trace_invoke._langsmith_traceable", lambda: _passthrough_traceable
    )
    monkeypatch.setattr(
        "pfa.trace_invoke._invoke_tool_raw",
        lambda _n, _a: {"delegated": True},
    )
    assert invoke_tool_traced("ledger_summary", {}) == {"delegated": True}

    def raw_raises(*_a, **_k):
        raise ValueError("boom")

    monkeypatch.setattr("pfa.trace_invoke._invoke_tool_raw", raw_raises)
    with pytest.raises(ValueError, match="boom"):
        invoke_tool_traced("ledger_summary", {})


def test_tracing_enabled_langsmith_missing_falls_back_like_raw(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setattr("pfa.trace_invoke._langsmith_traceable", lambda: None)
    with pytest.raises(ValueError, match="unknown tool"):
        invoke_tool_traced("not_a_real_tool", {})
