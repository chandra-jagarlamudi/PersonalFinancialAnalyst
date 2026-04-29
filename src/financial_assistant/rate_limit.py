"""Per-client sliding-window rate limiter middleware.

T-043: Rate limit by session_id (browser) or MCP API key (MCP).
Default 60 req/min, configurable via RATE_LIMIT_PER_MIN env var.
In-memory; asyncio event loop is single-threaded, no lock needed.
"""

import time
from collections import defaultdict, deque
from typing import DefaultDict, Deque

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from financial_assistant.config import get_settings

log = structlog.get_logger()

_SESSION_COOKIE = "session_id"
_MCP_PATHS = {"/sse", "/messages"}

# In-memory sliding window: client_key → deque of monotonic timestamps
_windows: DefaultDict[str, Deque[float]] = defaultdict(deque)

_WINDOW_SECS = 60.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """T-043: Sliding window rate limiter keyed by session_id or MCP API key."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        if settings.disable_auth:
            return await call_next(request)

        path = request.url.path

        # Derive client key
        if path in _MCP_PATHS:
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                # MCPApiKeyMiddleware will reject this request; don't rate-limit
                return await call_next(request)
            client_key = "mcp:" + auth_header[len("Bearer "):]
        else:
            session_id = request.cookies.get(_SESSION_COOKIE)
            if not session_id:
                # SessionAuthMiddleware will reject this; don't rate-limit
                return await call_next(request)
            client_key = "session:" + session_id

        limit = settings.rate_limit_per_min
        now = time.monotonic()
        window_start = now - _WINDOW_SECS

        # Slide window: evict timestamps older than window
        bucket = _windows[client_key]
        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        reset_in = max(1, int(bucket[0] + _WINDOW_SECS - now) + 1) if bucket else 1

        if len(bucket) >= limit:
            log.warning(
                "rate_limit.exceeded",
                path=path,
                # Log only enough of the key to identify client type, not the full token
                client_type="mcp" if path in _MCP_PATHS else "browser",
            )
            resp = Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
            )
            resp.headers["Retry-After"] = str(reset_in)
            resp.headers["X-RateLimit-Limit"] = str(limit)
            resp.headers["X-RateLimit-Remaining"] = "0"
            resp.headers["X-RateLimit-Reset"] = str(reset_in)
            return resp

        bucket.append(now)
        remaining = limit - len(bucket)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
        return response
