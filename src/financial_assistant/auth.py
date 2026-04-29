"""Google OAuth 2.0 authentication routes and middleware.

Routes:
    GET  /auth/login     → redirect to Google consent screen
    GET  /auth/callback  → exchange code, validate email, issue session cookie
    POST /auth/logout    → delete session row, clear cookie
    GET  /auth/me        → return { email } for current session
    GET  /auth/status    → return { auth_enabled } (for UI)
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from financial_assistant.config import get_settings
from financial_assistant.db import get_session
from financial_assistant.models import UserSession
from financial_assistant.queries import get_statement_by_hash  # noqa: F401 (unused here)
from sqlalchemy import delete, select, text

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSION_COOKIE = "session_id"
_CSRF_COOKIE = "csrf_token"
_STATE_COOKIE = "oauth_state"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _redirect_uri(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/auth/callback"


# ── T-031: GET /auth/login ────────────────────────────────────────────────────


@router.get("/login")
async def login(request: Request) -> Response:
    settings = get_settings()
    state = secrets.token_urlsafe(32)

    client = AsyncOAuth2Client(
        client_id=settings.google_client_id,
        redirect_uri=_redirect_uri(request),
        scope="openid email",
    )
    url, _ = client.create_authorization_url(
        GOOGLE_AUTH_URL,
        state=state,
        access_type="online",
    )

    log.info("auth.login_redirect", state=state[:8] + "...")

    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=False,  # set True in prod behind HTTPS
    )
    return response


# ── T-032: GET /auth/callback ─────────────────────────────────────────────────


@router.get("/callback")
async def callback(request: Request) -> Response:
    settings = get_settings()

    code = request.query_params.get("code")
    state_param = request.query_params.get("state")
    state_cookie = request.cookies.get(_STATE_COOKIE)

    if not code or not state_param or not state_cookie:
        log.warning("auth.callback_missing_params")
        return JSONResponse({"detail": "Missing required OAuth parameters"}, status_code=400)

    if not secrets.compare_digest(state_param, state_cookie):
        log.warning("auth.callback_state_mismatch")
        return JSONResponse({"detail": "Invalid state parameter"}, status_code=400)

    client = AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=_redirect_uri(request),
    )

    token = await client.fetch_token(GOOGLE_TOKEN_URL, code=code)
    userinfo_response = await client.get(GOOGLE_USERINFO_URL)
    userinfo = userinfo_response.json()
    email = userinfo.get("email", "")

    # ── T-033: email allowlist check ──────────────────────────────────────────
    if email.lower() != settings.allowed_user_email.lower():
        log.warning("auth.login_forbidden", email_domain=email.split("@")[-1] if "@" in email else "unknown")
        return JSONResponse(
            {"detail": f"Account not authorized. Only {settings.allowed_user_email} may log in."},
            status_code=403,
        )

    # ── T-034: create session + set HttpOnly cookie ────────────────────────────
    session_id = uuid.uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_expiry_days)

    async with get_session() as db:
        db_session = UserSession(
            id=session_id,
            user_email=email,
            expires_at=expires_at,
        )
        db.add(db_session)

    log.info("auth.login_success", user_email=email)

    csrf_token = secrets.token_urlsafe(32)

    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(_STATE_COOKIE)
    response.set_cookie(
        _SESSION_COOKIE,
        str(session_id),
        max_age=settings.session_expiry_days * 86400,
        httponly=True,
        secure=False,  # set True in prod
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        _CSRF_COOKIE,
        csrf_token,
        max_age=settings.session_expiry_days * 86400,
        httponly=False,  # JS-readable for double-submit pattern
        secure=False,
        samesite="strict",
        path="/",
    )
    return response


# ── T-036: POST /auth/logout ──────────────────────────────────────────────────


@router.post("/logout")
async def logout(request: Request) -> Response:
    session_id = request.cookies.get(_SESSION_COOKIE)

    if session_id:
        try:
            async with get_session() as db:
                await db.execute(
                    delete(UserSession).where(UserSession.id == uuid.UUID(session_id))
                )
            log.info("auth.logout", session_prefix=session_id[:8])
        except Exception:
            pass

    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(_SESSION_COOKIE, path="/")
    response.delete_cookie(_CSRF_COOKIE, path="/")
    return response


# ── T-039: GET /auth/me ───────────────────────────────────────────────────────


@router.get("/me")
async def me(request: Request) -> Response:
    email = getattr(request.state, "user_email", None)
    if not email:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return JSONResponse({"email": email})


# ── T-040: GET /auth/status ───────────────────────────────────────────────────


@router.get("/status")
async def auth_status() -> Response:
    settings = get_settings()
    return JSONResponse({"auth_enabled": not settings.disable_auth})


# ── T-035: session middleware helper ─────────────────────────────────────────


async def validate_session(request: Request) -> str | None:
    """Validate browser session cookie. Returns user_email or None."""
    settings = get_settings()

    if settings.disable_auth:
        return settings.allowed_user_email

    session_id = request.cookies.get(_SESSION_COOKIE)
    if not session_id:
        return None

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None

    async with get_session() as db:
        result = await db.execute(
            select(UserSession.user_email).where(
                UserSession.id == sid,
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
        row = result.scalar_one_or_none()

    return row
