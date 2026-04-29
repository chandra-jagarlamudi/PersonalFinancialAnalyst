---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: auth
status: Draft
---

# Kit: Auth

Google OAuth 2.0 authentication for single-user personal finance server. All HTTP endpoints protected; only the configured user's identity may access the system.

## Requirements

### R1 — OAuth Login Flow
Server exposes OAuth 2.0 authorization code flow endpoints.
- `GET /auth/login` → redirects to Google's OAuth consent screen
- `GET /auth/callback?code=...&state=...` → exchanges code for tokens, issues session
- State parameter used to prevent CSRF
- Acceptance: Browser hitting `/auth/login` completes Google sign-in and lands on success page

### R2 — Single-User Identity Enforcement
Only the configured user email may authenticate.
- `ALLOWED_USER_EMAIL` env var holds the single authorized email
- After OAuth callback, verified email compared against `ALLOWED_USER_EMAIL`
- Non-matching email returns 403 with clear error; token not issued
- Acceptance: Authenticating with a different Google account returns 403; correct account succeeds

### R3 — Session Issuance via HttpOnly Cookie
On successful OAuth, server creates a server-side session and issues a session cookie.
- On successful OAuth callback, server creates a server-side session record in Postgres `sessions` table
- Server sets a session cookie: `HttpOnly; Secure; SameSite=Strict; Path=/`
- No token or credential returned in response body
- OAuth callback redirects browser to app root after setting cookie
- Session expiry controlled by `SESSION_EXPIRY_DAYS` env var (default: 30), stored as `expires_at` in sessions table
- Acceptance: After OAuth login, browser has session cookie; no credential visible in response body or JavaScript

### R4 — Browser Request Authentication Middleware
All non-auth HTTP endpoints (browser path) require a valid server-side session.
- Middleware reads session cookie from incoming request
- Validates session by querying Postgres `sessions` table: session must exist and not be expired
- Missing cookie → 401
- Cookie present but no matching unexpired session row → 401
- Valid session → request proceeds with `user_email` in request context
- When `DISABLE_AUTH=true`: middleware is bypassed; all requests treated as authenticated with `ALLOWED_USER_EMAIL`
- Acceptance: Request without session cookie to `/upload` returns 401; request with valid session cookie proceeds; `DISABLE_AUTH=true` skips check

### R5 — Session Revocation
Sessions can be invalidated without waiting for expiry.
- `POST /auth/logout` reads session cookie, deletes corresponding row from `sessions` table
- After deletion, the session cookie is invalid on next request (middleware finds no matching row)
- Server also instructs browser to clear the session cookie via `Set-Cookie` with expired `Max-Age`
- No in-memory state. Revocation survives server restarts.
- Acceptance: Session valid before logout; same session cookie rejected after logout even if server restarts between the two calls

### R6 — CSRF Protection
State-changing endpoints require CSRF protection via double-submit cookie pattern.
- All state-changing endpoints (POST /upload, POST /auth/logout, POST /chat, POST /tools/*) require CSRF protection
- Double-submit cookie pattern: server sets a non-HttpOnly CSRF token cookie; client reads it via JavaScript and submits it as a request header (`X-CSRF-Token`)
- Server middleware validates that the header value matches the cookie value
- GET endpoints and the OAuth flow endpoints are exempt
- `DISABLE_AUTH=true` also disables CSRF validation for dev mode
- Acceptance: POST /upload without X-CSRF-Token header returns 403; with matching header proceeds

### R7 — Current User Endpoint
Authenticated browser clients can retrieve the active session's user identity.
- `GET /auth/me` reads the session cookie and returns `{ email: string }` from the active session
- Returns 401 if no valid session
- Consumed by UI to display user email in header without storing identity client-side
- Acceptance: Authenticated browser calls `GET /auth/me` → response contains correct email; unauthenticated call returns 401

### R8 — MCP API Key Authentication
Programmatic MCP clients (non-browser) authenticate via a pre-shared API key.
- `MCP_API_KEY` env var holds a long-lived opaque token configured on both server and MCP client
- MCP endpoints (`GET /sse`, `POST /messages`) validate `Authorization: Bearer <MCP_API_KEY>` header
- Invalid or missing key → 401
- MCP API key is entirely separate from the browser OAuth session flow — no OAuth required for MCP clients
- `DISABLE_AUTH=true` also bypasses MCP API key validation for dev mode
- Acceptance: `/sse` with correct `MCP_API_KEY` in Authorization header connects; wrong key returns 401

## Cross-References
- infra: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_USER_EMAIL`, `MCP_API_KEY`, `SESSION_EXPIRY_DAYS`, `DISABLE_AUTH` env vars
- observability: auth events (login, logout, 401, 403) emitted as structured log entries
- mcp: MCP endpoints use R8 API key auth; browser endpoints use R4 session cookie auth
- ingestion: upload endpoint uses R4 session cookie middleware
- storage: sessions table (R6 in kit-storage.md) holds server-side session records
- ui: `GET /auth/me` (R7) consumed by UI header; `GET /auth/status` returns `{ auth_enabled }` derived from `DISABLE_AUTH`
