# Personal Financial Analyst

Self-hosted personal finance stack: ingest bank and credit card statements (CSV and targeted PDFs), normalize them into **PostgreSQL**, and use a **backend-run AI agent** with an **MCP-shaped tool layer** for budgeting, charts, recurring spend, anomalies, and chat grounded in your ledger.

**Product spec:** [docs/PRD.md](docs/PRD.md) (canonical copy) · [Issue #1 — PRD discussion](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/1)

**Implementation slices (vertical, end-to-end):**

| # | Topic | Issue | Status |
|---:|---|---|---|
| 0 | Local dev infra (Docker Compose, Postgres, volumes, wiring) | [#2](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/2) | **Shipped** |
| 1 | Auth + localhost-only app shell | [#3](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/3) | Planned |
| 2 | Ledger foundation (institutions, accounts, categories) | [#4](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/4) | Planned |
| 3 | Async jobs + step-level status UI | [#5](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/5) | Planned |
| 4 | CSV ingestion + dedupe | [#6](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/6) | **Implemented** |
| 5 | Raw file storage + hash idempotency + purge | [#7](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/7) | **Implemented** |
| 6 | Budgeting (envelope monthly + suggest + status) | [#8](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/8) | **Implemented** |
| 7 | Rules-first categorization + rule proposals | [#9](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/9) | Planned |
| 8 | Recurring detection + UI | [#10](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/10) | Planned |
| 9 | Anomaly detection + UI | [#11](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/11) | Planned |
| 10 | Agent + tools + streaming chat | [#12](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/12) | **Implemented** |
| 11 | LangSmith tracing | [#13](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/13) | **Implemented** |
| 12 | Targeted credit card PDF (HITL) | [#14](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/14) | Planned |

**Slice 0** in this repo: [`compose.yaml`](compose.yaml), [`.env.example`](.env.example), [`scripts/verify-infra.sh`](scripts/verify-infra.sh), [`Makefile`](Makefile) (`verify-infra`). Tracked in [issue #2](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/2); shipped on **`main`** via [#15](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/pull/15) with follow-ups in [#17](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/pull/17). Canonical PRD file added in [#16](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/pull/16).

**Slice 4** ([issue #6](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/6)): [`backend/`](backend/) FastAPI app with `POST /ingest/csv` (multipart form field `account_id` + CSV `file`, **max 10 MiB** per upload), deterministic `dedupe_fingerprint` (SHA-256) and a Postgres `UNIQUE` constraint so replays increment `skipped_duplicates`. CSV columns: `transaction_date`, `amount`, `description`; optional `posted_date`, `currency` (default USD). Schema bootstrap runs once at API startup (not per request). Compose service **`api`** listens on `127.0.0.1:${API_PORT:-8000}` (`GET /health`). Tests: install deps under `backend/` and run `make test-backend` with `DATABASE_URL` pointing at the Compose database.

**Slice 6** ([issue #8](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/8)): Envelope budgets per calendar month and category. **`categories`** table (`slug`, `name`) with `POST /categories` and `GET /categories`. **`budgets`** rows keyed by `(category_id, month)` where `month` is `YYYY-MM-01`; `PUT /budgets/{year_month}` upserts `{items: [{category_id, amount}]}`, `GET /budgets/{year_month}` lists caps. **`GET /budgets/{year_month}/status`** sums expenses (`amount < 0`) from **`transactions.category_id`** MTD (optional `as_of` query) and returns linear **projected** month spend plus remaining amounts. **`POST /budgets/{year_month}/suggest`** proposes caps from prior-window expense totals divided by `lookback_months` (default 6). Categorization rules remain slice 7; link spending by setting `transactions.category_id`.

**Slice 10** ([issue #12](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/12)): Embedded **MCP-shaped** read tools plus **SSE streaming chat**. **`GET /chat/tools`** returns JSON-schema manifests (`ledger_summary`: aggregate counts and expense/income totals, optional `account_id`). **`POST /chat/stream`** accepts `{ "message": "..." }` and emits **`text/event-stream`** frames (`tool_call`, `tool_result`, `delta`, `done`). The MVP planner is **deterministic** (keyword routing); swap-in LLM planner later without changing tool contracts.

**Slice 11** ([issue #13](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/13)): **Optional LangSmith** wrapping on **`invoke_tool`** via **`LANGCHAIN_TRACING_V2=true`** (+ **`LANGCHAIN_API_KEY`**, **`LANGCHAIN_PROJECT`**). When tracing is off or **`langsmith`** is missing, behavior matches the slice 10 path. See [`.env.example`](.env.example).

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

You can: bring up **Postgres locally** ([Getting started](#getting-started)), then run the full stack once later slices land—log in, upload **CSV**, watch ingestion complete with step status, see transactions and charts, set **monthly budgets** with suggestions, see **recurring** and **anomaly** lists, and chat with the agent using tools—without duplicate transactions on retry/re-upload.

---

## Architecture (conceptual)

- **Frontend**: Vite + React + TypeScript; dedicated **Upload** surface plus **Chat**; charts for cashflow, categories, budgets, recurring, anomalies.
- **Backend**: single service hosting HTTP API, **Postgres-backed job queue**, ingestion pipeline, analytics queries, **LLM client abstraction** (pluggable providers), embedded **tool** layer, **LangSmith** hooks.
- **Data**: PostgreSQL as system of record; **raw statement files** live on a host bind mount consumed by **`api`** (`./data/raw-statements` by default, gitignored). Service **`db`** (PostgreSQL 16) keeps database files in named volume **`pgdata`** only.

---

## Getting started

### Local database (slice [#2](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/2))

Prerequisites: [Docker](https://docs.docker.com/get-docker/) with Compose v2.

From the repository root:

1. Copy the env template and edit secrets if you want non-default passwords:

   ```bash
   cp .env.example .env
   ```

2. Create the raw-statement bind-mount directory (gitignored; Compose also creates it when missing on many setups):

   ```bash
   mkdir -p data/raw-statements
   ```

3. Start Postgres (and optionally the **`api`** service from slice 4). Compose loads **`.env`** from this directory for variable substitution; the **`db`** service also reads that file so credentials stay in sync. The Compose **project name** defaults to this folder’s name (no fixed `name:` in [`compose.yaml`](compose.yaml)), so separate clones keep distinct containers/volumes. Override with [`docker compose --project-name …`](https://docs.docker.com/compose/how-tos/project-name/) if needed.

   ```bash
   docker compose up -d
   ```

   Database only: `docker compose up -d db`. With API: use the same command (Compose starts **`db`** and **`api`**; **`api`** waits until **`db`** is healthy).

   Optional explicit file: `docker compose --env-file .env up -d`.

   Postgres is published on **`127.0.0.1:${POSTGRES_PORT}`** only (not all interfaces); change [`compose.yaml`](compose.yaml) if you intentionally need LAN access.

   Wait until Postgres is ready: `docker compose ps` should show **`db`** as **`healthy`**, or use `docker compose up -d --wait` if your Compose version supports it.

4. From the host, connect using **`DATABASE_URL`** in `.env` (see `.env.example`; defaults use `127.0.0.1` and **`POSTGRES_PORT`**).

5. Run the automated checks (compose config, readiness, `SELECT 1`, persistence across **`db` restart**, raw mount):

   ```bash
   make verify-infra
   ```

   This runs [`scripts/verify-infra.sh`](scripts/verify-infra.sh) against **`.env.example`**. **Teardown:** if **`db` was not running** when the script started, it finishes with **`docker compose down`** (no `-v`, **`pgdata`** kept). If **`db` was already up**, the script **leaves your stack running**—only inspects it—so you are not surprised by missing teardown. To drop volumes when the script does tear down: `./scripts/verify-infra.sh --teardown-volumes`.

**Teardown**

- Stop containers, **keep** Postgres data: `docker compose down`
- Stop and **delete** the **`pgdata`** volume: `docker compose down -v`

**Next slice:** [#3](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/3) (auth + localhost-only app shell).

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
