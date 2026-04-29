"""Tests for rate limiter and tracing init.

T-043: 61st request within window returns 429; first of next window succeeds
T-044: init_tracing no-ops with warning when API key absent
"""

import time
from collections import defaultdict, deque
from unittest.mock import MagicMock, patch

import pytest
import structlog.testing
from starlette.responses import Response

from financial_assistant.rate_limit import RateLimitMiddleware, _windows
from financial_assistant.tracing import init_tracing, is_enabled


# ── T-043: Rate limiter ──────────────────────────────────────────────────────


def _make_request(path: str = "/protected", session_id: str = "sid-test"):
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = path
    req.method = "GET"
    req.cookies = {"session_id": session_id}
    req.headers = {}
    req.state = MagicMock()
    return req


def _settings(limit: int = 60):
    s = MagicMock()
    s.disable_auth = False
    s.rate_limit_per_min = limit
    return s


async def _dispatch(middleware, request, settings_mock=None):
    call_next = MagicMock(return_value=Response(status_code=200))
    # call_next must be a coroutine
    import asyncio

    async def _call_next(req):
        return Response(status_code=200)

    sm = settings_mock or _settings()
    with patch("financial_assistant.rate_limit.get_settings", return_value=sm):
        return await middleware.dispatch(request, _call_next)


async def test_rate_limit_allows_requests_under_limit():
    """T-043: Requests under the limit pass with correct headers."""
    from unittest.mock import AsyncMock

    _windows.clear()
    middleware = RateLimitMiddleware(AsyncMock())
    req = _make_request(session_id="under-limit-sid")

    resp = await _dispatch(middleware, req, _settings(limit=5))
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "5"
    assert int(resp.headers["X-RateLimit-Remaining"]) == 4


async def test_rate_limit_returns_429_on_61st_request():
    """T-043: 61st request within 60s returns 429 with Retry-After."""
    from unittest.mock import AsyncMock

    _windows.clear()
    middleware = RateLimitMiddleware(AsyncMock())
    sid = "limit-test-sid"

    # Pre-fill window with 60 timestamps to simulate 60 prior requests
    now = time.monotonic()
    bucket = _windows["session:" + sid]
    for _ in range(60):
        bucket.append(now)

    req = _make_request(session_id=sid)
    resp = await _dispatch(middleware, req, _settings(limit=60))

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.headers["X-RateLimit-Limit"] == "60"
    assert resp.headers["X-RateLimit-Remaining"] == "0"
    assert int(resp.headers["Retry-After"]) >= 1


async def test_rate_limit_resets_after_window():
    """T-043: First request of next window succeeds (old timestamps expired)."""
    from unittest.mock import AsyncMock

    _windows.clear()
    middleware = RateLimitMiddleware(AsyncMock())
    sid = "reset-test-sid"

    # Pre-fill with 60 timestamps that are 61 seconds ago (outside window)
    old_time = time.monotonic() - 61.0
    bucket = _windows["session:" + sid]
    for _ in range(60):
        bucket.append(old_time)

    req = _make_request(session_id=sid)
    resp = await _dispatch(middleware, req, _settings(limit=60))

    # All old timestamps should be evicted; request should succeed
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Remaining"] == "59"


async def test_rate_limit_mcp_path_uses_bearer_key():
    """T-043: MCP paths keyed by Bearer token, not session cookie."""
    from unittest.mock import AsyncMock

    _windows.clear()
    middleware = RateLimitMiddleware(AsyncMock())

    req = MagicMock()
    req.url = MagicMock()
    req.url.path = "/sse"
    req.method = "GET"
    req.cookies = {}
    req.headers = {"authorization": "Bearer my-mcp-key"}
    req.state = MagicMock()

    # Pre-fill window for mcp: key
    now = time.monotonic()
    bucket = _windows["mcp:my-mcp-key"]
    for _ in range(5):
        bucket.append(now)

    resp = await _dispatch(middleware, req, _settings(limit=5))
    assert resp.status_code == 429


async def test_rate_limit_skipped_when_disable_auth():
    """T-043: DISABLE_AUTH=true bypasses rate limiting."""
    from unittest.mock import AsyncMock

    _windows.clear()
    middleware = RateLimitMiddleware(AsyncMock())
    sid = "bypass-sid"

    # Pre-fill past limit
    now = time.monotonic()
    bucket = _windows["session:" + sid]
    for _ in range(100):
        bucket.append(now)

    req = _make_request(session_id=sid)
    s = _settings(limit=60)
    s.disable_auth = True

    resp = await _dispatch(middleware, req, s)
    assert resp.status_code == 200


# ── T-044: LangSmith tracing init ────────────────────────────────────────────


def test_tracing_disabled_when_no_key():
    """T-044: Missing API key logs warning and leaves tracing disabled."""
    import financial_assistant.tracing as tracing_mod

    tracing_mod._enabled = False

    with structlog.testing.capture_logs() as logs:
        init_tracing("", "test-project")

    assert not is_enabled()
    warn_logs = [l for l in logs if l.get("event") == "tracing.disabled"]
    assert len(warn_logs) == 1
    assert warn_logs[0]["reason"] == "LANGSMITH_API_KEY not set"


def test_tracing_enabled_when_key_present(monkeypatch):
    """T-044: Valid API key enables tracing and logs confirmation."""
    import os

    import financial_assistant.tracing as tracing_mod

    tracing_mod._enabled = False

    with structlog.testing.capture_logs() as logs:
        init_tracing("ls__fake-key", "my-project")

    assert is_enabled()
    info_logs = [l for l in logs if l.get("event") == "tracing.enabled"]
    assert len(info_logs) == 1
    assert info_logs[0]["project"] == "my-project"

    # Clean up
    tracing_mod._enabled = False
    for env_key in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT"):
        os.environ.pop(env_key, None)


def test_trace_span_noop_when_disabled():
    """T-044: trace_span yields None and doesn't raise when tracing is disabled."""
    from financial_assistant.tracing import trace_span
    import financial_assistant.tracing as tracing_mod

    tracing_mod._enabled = False

    result = None
    with trace_span("test-span") as run:
        result = run

    assert result is None
