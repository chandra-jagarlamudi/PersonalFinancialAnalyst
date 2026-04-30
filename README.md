# Personal Financial Analyst

Self-hosted personal finance stack: ingest bank and credit card statements (CSV and targeted PDFs), normalize them into **PostgreSQL**, and use a **backend-run AI agent** with an **MCP-shaped tool layer** for budgeting, charts, recurring spend, anomalies, and chat grounded in your ledger.

**Product spec:** [PRD #1 — Personal Finance MCP server + agent-driven UI (self-hosted MVP)](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/1)

**Implementation slices (vertical, end-to-end):**

| # | Topic | Issue |
|---:|---|---|
| 0 | Local dev infra (Docker Compose, Postgres, volumes, wiring) | [#2](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/2) |
| 1 | Auth + localhost-only app shell | [#3](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/3) |
| 2 | Ledger foundation (institutions, accounts, categories) | [#4](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/4) |
| 3 | Async jobs + step-level status UI | [#5](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/5) |
| 4 | CSV ingestion + dedupe | [#6](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/6) |
| 5 | Raw file storage + hash idempotency + purge | [#7](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/7) |
| 6 | Budgeting (envelope monthly + suggest + status) | [#8](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/8) |
| 7 | Rules-first categorization + rule proposals | [#9](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/9) |
| 8 | Recurring detection + UI | [#10](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/10) |
| 9 | Anomaly detection + UI | [#11](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/11) |
| 10 | Agent + tools + streaming chat | [#12](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/12) |
| 11 | LangSmith tracing | [#13](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/13) |
| 12 | Targeted credit card PDF (HITL) | [#14](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/14) |

---

## MVP (what you get first)

The MVP is **single-user, self-hosted**, optimized for a trustworthy ledger and a budgeting-first UI—not for multi-tenant SaaS.

### Core capabilities

- **Ingestion**
  - **CSV** statements end-to-end: upload → async job → normalized transactions in Postgres.
  - **One targeted credit card PDF** format (after a sample statement is agreed for parser tests); generic “any PDF” is explicitly later work.
  - **Async jobs** backed by Postgres, with **step-level status** and counts; UI **polls** job progress (no streaming of job steps in MVP).
  - **Statement-level** idempotency (content hash) and **transaction-level** dedupe (deterministic fingerprint + uniqueness).
  - **Raw files** on disk with DB metadata; **soft-delete** and **permanent purge** (DB + files).

- **Ledger & accounts**
  - Institutions, accounts, **account aliases**, categories with **stable internal ids** (default taxonomy + user customization).

- **Budgeting & analytics**
  - **Envelope-style monthly budgets** per category, **month-to-date** views with simple **projection**, and **suggest from history** (aggregate-based, no LLM required).
  - Cashflow and category views over time.
  - **Recurring** charges: same merchant + similar amount, **monthly** cadence, **≥3** occurrences (deterministic).
  - **Anomalies**: deterministic signals + simple robust stats; optional agent **explanations** after detection.

- **Agent & tools**
  - **Backend-run** agent; tools are **MCP-shaped** but **embedded in the backend** (not a separate MCP process for MVP).
  - **High-level read tools** plus a **restricted read-only SQL** escape hatch for development and deep questions.
  - **Streaming chat** in the UI.
  - **Confirm-before-write** for any mutating tool path.
  - **Privacy default**: aggregates to the model by default; **line-item context only on explicit drilldown**.
  - **LangSmith** for tracing agent and tool calls.

- **Security posture (MVP)**
  - **Password login** + session cookie.
  - **Localhost-only** binding by default; exposing beyond localhost is a deliberate later step (e.g. reverse proxy + TLS).

### Definition of done (MVP demo)

You can: run the stack locally (see slice [#2](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/2)), log in, upload **CSV**, watch ingestion complete with step status, see transactions and charts, set **monthly budgets** with suggestions, see **recurring** and **anomaly** lists, and chat with the agent using tools—without duplicate transactions on retry/re-upload.

---

## Architecture (conceptual)

- **Frontend**: Vite + React + TypeScript; dedicated **Upload** surface plus **Chat**; charts for cashflow, categories, budgets, recurring, anomalies.
- **Backend**: single service hosting HTTP API, **Postgres-backed job queue**, ingestion pipeline, analytics queries, **LLM client abstraction** (pluggable providers), embedded **tool** layer, **LangSmith** hooks.
- **Data**: PostgreSQL as system of record; **raw statement files** on a mounted volume/path suitable for Docker/local dev.

---

## Getting started

Until the repo contains the full app again, follow the **vertical slices** in order (especially **#2** for Compose + Postgres + volumes). When `docker compose` and env templates land, this section should be updated with exact commands—tracked in [#2](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/2).

---

## Future features (post-MVP)

These are **explicitly out of scope** for the MVP PRD or natural next steps after it:

- **Multi-tenant SaaS**: billing, orgs, enterprise SSO, row-level security hardening, abuse controls.
- **Bank linking**: Plaid / open banking / institution APIs instead of file upload.
- **Broad PDF support**: institution-agnostic PDF parsing beyond the first targeted card format; richer OCR/table pipelines as needed.
- **Real-time job streaming**: SSE/WebSocket for ingestion step updates (MVP uses polling).
- **Full observability stack**: metrics/tracing/logging beyond step-level job records + LangSmith.
- **Stricter production exposure**: HTTPS reverse proxy, tighter CSRF/CORS, rate limits, and possibly **removing or locking down** the read-only SQL tool when not on localhost.
- **Advanced budgeting**: rollovers, multi-month envelopes, goals/debt snowball, scenario planning.
- **Richer recurring & anomaly models**: weekly/annual cadences, merchant clustering across name variants, more sophisticated stats/ML—still with explainable UI.
- **Standalone MCP server**: same tool schemas exposed over stdio/HTTP for external agent runtimes (today: embedded for speed of iteration).
- **BYOK / per-user provider keys** in UI, encrypted at rest (single-user MVP can start with `.env`).

---

## Disclaimer

This project helps you **organize and analyze your own data**. It is **not** financial, legal, or tax advice. You are responsible for securing your machine, backups, and any keys (LLM, LangSmith, database).
