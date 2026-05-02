"""Authentication routes for the single-user app shell."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from pfa.auth import (
    apply_session_cookie,
    auth_settings,
    clear_session_cookie,
    create_session,
    optional_session,
    revoke_session,
    verify_login,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class SessionState(BaseModel):
    authenticated: bool
    username: str | None = None


@router.get("/session", response_model=SessionState)
def get_session(request: Request):
    try:
        session = optional_session(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if session is None:
        return SessionState(authenticated=False, username=None)
    return SessionState(authenticated=True, username=session.username)


@router.post("/login", response_model=SessionState)
def post_login(body: LoginBody, response: Response):
    try:
        auth_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not verify_login(body.username, body.password):
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = create_session(body.username.strip())
    apply_session_cookie(response, token)
    return SessionState(authenticated=True, username=body.username.strip())


@router.post("/logout", status_code=204)
def post_logout(request: Request):
    response = Response(status_code=204)
    token = request.cookies.get(auth_settings().cookie_name)
    if token:
        revoke_session(token)
    clear_session_cookie(response)
    return response
