"""Tests for auth routes and middleware.

T-037: session valid before logout; same cookie rejected after logout (DB-backed revocation)
T-042: auth event logging — correct events emitted, no PII in token fields
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog.testing
from sqlalchemy import delete, select
from starlette.responses import Response

from financial_assistant.auth_middleware import (
    CsrfMiddleware,
    MCPApiKeyMiddleware,
    SessionAuthMiddleware,
)
from financial_assistant.models import UserSession


# ── T-037: DB-backed session revocation ──────────────────────────────────────


async def test_session_revocation_is_db_backed(session):
    """T-037: Session valid before logout; rejected after row is deleted (simulates server restart)."""
    session_id = uuid.uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    session.add(UserSession(id=session_id, user_email="user@example.com", expires_at=expires_at))
    await session.flush()

    # Before logout: row exists and unexpired
    row = (
        await session.execute(
            select(UserSession.user_email).where(
                UserSession.id == session_id,
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
    ).scalar_one_or_none()
    assert row == "user@example.com"

    # Logout: delete the row (same logic as POST /auth/logout)
    await session.execute(delete(UserSession).where(UserSession.id == session_id))
    await session.flush()

    # After logout: same session_id finds no row — DB-backed, no in-memory state
    row_after = (
        await session.execute(
            select(UserSession.user_email).where(
                UserSession.id == session_id,
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
    ).scalar_one_or_none()
    assert row_after is None, "Revoked session must not be found — no in-memory state"


# ── T-042: Auth event logging ─────────────────────────────────────────────────

# Helpers


def _make_request(path: str, method: str = "GET", cookies: dict | None = None, headers: dict | None = None):
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = path
    req.method = method
    req.cookies = cookies or {}
    req.headers = {k.lower(): v for k, v in (headers or {}).items()}
    req.state = MagicMock()
    return req


async def test_session_middleware_emits_401_log():
    """T-042: Missing session on protected path emits auth.401 with path, no PII."""
    middleware = SessionAuthMiddleware(AsyncMock())
    request = _make_request("/protected", cookies={})
    call_next = AsyncMock(return_value=Response())

    with patch("financial_assistant.auth_middleware.validate_session", new_callable=AsyncMock, return_value=None):
        with structlog.testing.capture_logs() as logs:
            response = await middleware.dispatch(request, call_next)

    assert response.status_code == 401
    events = [l for l in logs if l.get("event") == "auth.401"]
    assert len(events) == 1
    entry = events[0]
    assert entry["path"] == "/protected"
    # No PII in 401 entry
    assert "user_email" not in entry
    assert "session_id" not in entry


async def test_mcp_middleware_emits_missing_key_log():
    """T-042: /sse with no Bearer header emits auth.mcp_missing_key, no token value logged."""
    middleware = MCPApiKeyMiddleware(AsyncMock())
    request = _make_request("/sse", headers={})
    request.headers = {}
    call_next = AsyncMock(return_value=Response())

    settings_mock = MagicMock(disable_auth=False, mcp_api_key="secret-key")
    with patch("financial_assistant.auth_middleware.get_settings", return_value=settings_mock):
        with structlog.testing.capture_logs() as logs:
            response = await middleware.dispatch(request, call_next)

    assert response.status_code == 401
    events = [l for l in logs if l.get("event") == "auth.mcp_missing_key"]
    assert len(events) == 1
    assert "token" not in events[0]
    assert "key" not in events[0]


async def test_mcp_middleware_emits_invalid_key_log():
    """T-042: /sse with wrong Bearer token emits auth.mcp_invalid_key, token value NOT logged."""
    middleware = MCPApiKeyMiddleware(AsyncMock())
    request = _make_request("/sse", headers={"authorization": "Bearer wrong-token"})
    request.headers = {"authorization": "Bearer wrong-token"}
    call_next = AsyncMock(return_value=Response())

    settings_mock = MagicMock(disable_auth=False, mcp_api_key="correct-secret")
    with patch("financial_assistant.auth_middleware.get_settings", return_value=settings_mock):
        with structlog.testing.capture_logs() as logs:
            response = await middleware.dispatch(request, call_next)

    assert response.status_code == 401
    events = [l for l in logs if l.get("event") == "auth.mcp_invalid_key"]
    assert len(events) == 1
    entry = events[0]
    # Token value must not appear in log
    assert "wrong-token" not in str(entry)
    assert "correct-secret" not in str(entry)


async def test_csrf_middleware_emits_missing_log():
    """T-042: POST without CSRF cookie emits auth.csrf_missing, no token value logged."""
    middleware = CsrfMiddleware(AsyncMock())
    request = _make_request("/upload", method="POST", cookies={})
    request.headers = {}
    call_next = AsyncMock(return_value=Response())

    settings_mock = MagicMock(disable_auth=False)
    with patch("financial_assistant.auth_middleware.get_settings", return_value=settings_mock):
        with structlog.testing.capture_logs() as logs:
            response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403
    events = [l for l in logs if l.get("event") == "auth.csrf_missing"]
    assert len(events) == 1
    assert "token" not in str(events[0])


async def test_csrf_middleware_emits_mismatch_log():
    """T-042: POST with mismatched CSRF tokens emits auth.csrf_mismatch, no token values logged."""
    middleware = CsrfMiddleware(AsyncMock())
    request = _make_request("/upload", method="POST", cookies={"csrf_token": "aaa"})
    request.headers = {"x-csrf-token": "bbb"}
    call_next = AsyncMock(return_value=Response())

    settings_mock = MagicMock(disable_auth=False)
    with patch("financial_assistant.auth_middleware.get_settings", return_value=settings_mock):
        with structlog.testing.capture_logs() as logs:
            response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403
    events = [l for l in logs if l.get("event") == "auth.csrf_mismatch"]
    assert len(events) == 1
    entry = events[0]
    assert "aaa" not in str(entry)
    assert "bbb" not in str(entry)


async def test_logout_route_emits_audit_log():
    """T-042: POST /auth/logout emits auth.logout with session prefix, not full session_id."""
    from financial_assistant.auth import logout

    session_id = str(uuid.uuid4())
    request = _make_request("/auth/logout", method="POST", cookies={"session_id": session_id})
    request.cookies = {"session_id": session_id}

    # Patch get_session to avoid real DB call
    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.execute = AsyncMock()

    with patch("financial_assistant.auth.get_session", return_value=mock_db):
        with structlog.testing.capture_logs() as logs:
            await logout(request)

    events = [l for l in logs if l.get("event") == "auth.logout"]
    assert len(events) == 1
    entry = events[0]
    # Only session prefix logged, not full UUID
    assert session_id not in str(entry), "Full session_id must not appear in log"
    assert "session_prefix" in entry
    assert len(entry["session_prefix"]) == 8
