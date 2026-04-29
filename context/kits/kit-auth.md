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

### R3 — Bearer Token Issuance
On successful OAuth, server issues a long-lived bearer token for API access.
- Bearer token is a signed JWT containing user email and expiry
- Token returned in callback response (JSON body)
- Token expiry configurable via env var (default: 30 days)
- Acceptance: Token is a valid JWT; decoding reveals correct claims

### R4 — Request Authentication Middleware
All non-auth HTTP endpoints require valid bearer token.
- Middleware extracts `Authorization: Bearer <token>` header
- Invalid or expired token → 401 with `WWW-Authenticate: Bearer` header
- Missing token → 401
- Valid token → request proceeds with user identity in request context
- Acceptance: Request without token to `/upload` returns 401; request with valid token proceeds

### R5 — Token Revocation
Tokens can be invalidated without waiting for expiry.
- `POST /auth/logout` with valid bearer token invalidates it
- Revoked tokens rejected by middleware even if not yet expired
- Revocation stored in-memory (single-user, single process — no DB persistence needed)
- Acceptance: Token valid before logout call; same token rejected after logout call

## Cross-References
- infra: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_USER_EMAIL` env vars
- observability: auth events (login, logout, 401, 403) emitted as structured log entries
- mcp: middleware applied to MCP SSE endpoints
- ingestion: middleware applied to upload endpoint
