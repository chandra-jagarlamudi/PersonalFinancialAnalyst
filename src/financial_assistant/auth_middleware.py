"""Authentication and CSRF middleware.

T-035: SessionAuthMiddleware — validates session cookie or DISABLE_AUTH bypass
T-038: CsrfMiddleware — double-submit cookie CSRF protection on POST routes
T-041: MCPApiKeyMiddleware — validates Authorization: Bearer header on MCP routes
T-042: auth event logging

These are Starlette BaseHTTPMiddleware instances added to the FastAPI app.
"""

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from financial_assistant.auth import validate_session
from financial_assistant.config import get_settings
from financial_assistant.logging_config import set_user_id

log = structlog.get_logger()

_SESSION_COOKIE = "session_id"
_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "x-csrf-token"

_CSRF_EXEMPT_PATHS = {"/auth/login", "/auth/callback"}
_MCP_PATHS = {"/sse", "/messages"}

# Paths that don't require browser session auth
_AUTH_EXEMPT_PATHS = {"/auth/login", "/auth/callback", "/auth/status", "/health"}


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """T-035: validate session cookie on non-exempt paths."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # MCP paths use separate API key auth — skip session check
        if path in _MCP_PATHS:
            return await call_next(request)

        if path in _AUTH_EXEMPT_PATHS or path.startswith("/auth/"):
            return await call_next(request)

        email = await validate_session(request)
        if email is None:
            log.warning("auth.401", path=path)
            return Response(
                content='{"detail":"Authentication required"}',
                status_code=401,
                media_type="application/json",
            )

        set_user_id(email)
        request.state.user_email = email
        return await call_next(request)


class CsrfMiddleware(BaseHTTPMiddleware):
    """T-038: double-submit cookie CSRF protection on POST routes."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        if settings.disable_auth:
            return await call_next(request)

        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        if request.url.path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # MCP routes use Bearer auth, not CSRF
        if request.url.path in _MCP_PATHS:
            return await call_next(request)

        csrf_cookie = request.cookies.get(_CSRF_COOKIE, "")
        csrf_header = request.headers.get(_CSRF_HEADER, "")

        if not csrf_cookie or not csrf_header:
            log.warning("auth.csrf_missing", path=request.url.path)
            return Response(
                content='{"detail":"CSRF token missing"}',
                status_code=403,
                media_type="application/json",
            )

        import secrets as _secrets
        if not _secrets.compare_digest(csrf_cookie, csrf_header):
            log.warning("auth.csrf_mismatch", path=request.url.path)
            return Response(
                content='{"detail":"CSRF token mismatch"}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)


class MCPApiKeyMiddleware(BaseHTTPMiddleware):
    """T-041: validate Bearer token on MCP routes /sse and /messages."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path not in _MCP_PATHS:
            return await call_next(request)

        settings = get_settings()

        if settings.disable_auth:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            log.warning("auth.mcp_missing_key", path=request.url.path)
            return Response(
                content='{"detail":"MCP API key required"}',
                status_code=401,
                media_type="application/json",
            )

        import secrets as _secrets
        provided_key = auth_header[len("Bearer "):]
        if not _secrets.compare_digest(provided_key, settings.mcp_api_key):
            log.warning("auth.mcp_invalid_key", path=request.url.path)
            return Response(
                content='{"detail":"Invalid MCP API key"}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
