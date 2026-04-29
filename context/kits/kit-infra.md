---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: infra
status: Draft
---

# Kit: Infra

Provisions local development environment — Postgres container, dev container, and environment configuration. No cloud resources required.

## Requirements

### R1 — Postgres Container
The system must provide a Postgres instance via Docker Compose for local development.
- Postgres 16+ runs in a named container
- Data persists across container restarts via a named Docker volume
- Container exposes port 5432 on localhost
- Health check confirms Postgres is accepting connections before dependent services start
- Acceptance: `docker compose up -d` starts Postgres; `psql` connects successfully on localhost:5432

### R2 — Application Container
The MCP server runs in its own container, linked to Postgres.
- Container built from Python 3.12+ base image
- Hot-reload enabled in dev mode (source mounted as volume)
- Depends on Postgres health check passing
- Acceptance: `docker compose up` starts both containers; server responds to HTTP requests

### R3 — Dev Container
A `.devcontainer/devcontainer.json` configuration enables VS Code / GitHub Codespaces dev container workflow.
- Dev container extends the same Docker Compose file
- Installs Python extensions, linters, formatters
- Port 8000 (server) and 5432 (Postgres) forwarded automatically
- Acceptance: "Reopen in Container" produces working dev environment with all tools available

### R4 — Environment Configuration
All secrets and environment-specific values loaded from environment variables; no hardcoded values.
- Required vars: `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_USER_EMAIL`, `LANGSMITH_API_KEY`, `ANTHROPIC_API_KEY`
- `.env.example` documents all required vars with descriptions; no real values
- `.env` is gitignored
- Acceptance: Server fails fast with clear error if any required var is missing

### R5 — Database Initialization
First-run database setup is automated.
- Running `docker compose up` applies all Alembic migrations automatically on startup
- Idempotent: re-running migrations on an already-initialized DB is safe
- Acceptance: Fresh `docker compose up` on empty volume produces a fully-migrated DB

## Cross-References
- storage: Postgres connection consumed by storage layer
- auth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_USER_EMAIL` vars defined here
- analytics: `ANTHROPIC_API_KEY` var defined here
- observability: `LANGSMITH_API_KEY` var defined here
