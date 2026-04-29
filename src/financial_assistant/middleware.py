"""HTTP middleware: request_id propagation, access logging, error capture.

Middleware stack (applied bottom-up in FastAPI):
    1. ErrorLoggingMiddleware  — outermost, catches unhandled exceptions
    2. RequestContextMiddleware — injects request_id + user_id, logs access
"""

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from financial_assistant.logging_config import set_request_id, set_user_id

log = structlog.get_logger()

# Patterns in log field values that hint at tokens/secrets — redact them.
_SENSITIVE_PATTERNS = (
    "Bearer ",
    "sk-ant-",
    "ls__",
)


def _redact_value(value: str) -> str:
    for pat in _SENSITIVE_PATTERNS:
        if pat in value:
            return "[REDACTED]"
    return value


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign request_id, propagate user_id, emit structured access log."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = str(uuid.uuid4())
        set_request_id(request_id)

        # user_id is populated by auth middleware later; default anonymous
        set_user_id("anonymous")

        start = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        user_id = request.state.user_email if hasattr(request.state, "user_email") else "anonymous"
        set_user_id(user_id)

        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions, log with full context, return 500.

    Sensitive data guard: Authorization header and raw file content are never
    logged — only exception type, message, and stack trace are recorded.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        try:
            return await call_next(request)
        except Exception as exc:
            log.error(
                "unhandled_exception",
                exc_info=exc,
                method=request.method,
                path=request.url.path,
            )
            return Response(
                content='{"detail":"Internal server error"}',
                status_code=500,
                media_type="application/json",
            )
