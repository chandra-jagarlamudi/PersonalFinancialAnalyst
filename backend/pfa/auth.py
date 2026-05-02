"""Single-user session auth helpers."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response
from psycopg.rows import dict_row

from pfa.db import connect


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password: str
    cookie_name: str
    cookie_secure: bool
    ttl_hours: int


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    username: str


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def auth_settings() -> AuthSettings:
    username = os.environ.get("PFA_AUTH_USERNAME", "admin").strip() or "admin"
    password = os.environ.get("PFA_AUTH_PASSWORD", "").strip()
    if not password:
        raise RuntimeError("PFA_AUTH_PASSWORD must be set")
    ttl_str = os.environ.get("PFA_SESSION_TTL_HOURS", "168").strip()
    try:
        ttl_hours = int(ttl_str)
    except ValueError:
        raise RuntimeError(f"PFA_SESSION_TTL_HOURS must be an integer, got '{ttl_str}'")
    if ttl_hours < 1:
        raise RuntimeError("PFA_SESSION_TTL_HOURS must be >= 1")
    return AuthSettings(
        username=username,
        password=password,
        cookie_name=os.environ.get("PFA_SESSION_COOKIE_NAME", "pfa_session").strip()
        or "pfa_session",
        cookie_secure=_env_flag("PFA_SESSION_COOKIE_SECURE", default=False),
        ttl_hours=ttl_hours,
    )


def verify_login(username: str, password: str) -> bool:
    settings = auth_settings()
    return hmac.compare_digest(username.strip(), settings.username) and hmac.compare_digest(
        password, settings.password
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    settings = auth_settings()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (username, token_hash, expires_at)
            VALUES (
              %s,
              %s,
              now() + (%s || ' hours')::interval
            )
            """,
            (username, _token_hash(token), settings.ttl_hours),
        )
        conn.commit()
    return token


def revoke_session(token: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash = %s",
            (_token_hash(token),),
        )
        conn.commit()


def optional_session(request: Request) -> SessionInfo | None:
    settings = auth_settings()
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username
                FROM auth_sessions
                WHERE token_hash = %s
                  AND expires_at > now()
                LIMIT 1
                """,
                (_token_hash(token),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                "UPDATE auth_sessions SET last_seen_at = now() WHERE id = %s",
                (row["id"],),
            )
        conn.commit()
    return SessionInfo(session_id=str(row["id"]), username=row["username"])


def require_authenticated(request: Request) -> SessionInfo:
    session = optional_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return session


def apply_session_cookie(response: Response, token: str) -> None:
    settings = auth_settings()
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.ttl_hours * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = auth_settings()
    response.delete_cookie(settings.cookie_name, path="/")
