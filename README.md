# Personal Financial Analyst

Personal Financial Analyst is a self-hosted personal finance system for people who want a trustworthy ledger first and AI-assisted analysis second. The project is built around a simple idea: raw statement data should be ingested into a durable PostgreSQL ledger with deterministic parsing, normalization, and deduplication before any higher-level budgeting, categorization, recurring-spend detection, or agent-driven analysis happens.

The long-term product direction is a budgeting-first web application with an embedded AI agent and an MCP-shaped tool layer. The current repository already includes a working backend service, Docker Compose-based local infrastructure, raw statement file storage, CSV ingestion, envelope budgeting, deterministic categorization rules, and recurring-charge detection. The canonical product vision lives in [docs/PRD.md](docs/PRD.md).

## What the project is trying to solve

Personal finance data is usually spread across different institutions, export formats, and inconsistent naming conventions. Spreadsheets work, but they require constant manual cleanup. Generic "chat with your finances" products often skip the hard parts: reliable ingestion, repeatable deduplication, stable categories, and privacy-conscious data handling.

This project is designed to solve that problem in layers:

1. **Ingest statements reliably.** Bring structured financial data into one canonical schema.
2. **Preserve trust in the ledger.** Prevent duplicate statements and duplicate transactions with deterministic hashing and uniqueness constraints.
3. **Make the ledger useful.** Support categories, budgets, recurring-spend detection, and future anomaly detection.
4. **Enable higher-level analysis safely.** Add an AI assistant on top of structured tools instead of letting an LLM guess from untrusted raw text.

## Current state of the repository

The repo is ahead of the old README in a few areas. Today it contains:

| Area | Status | Notes |
|---|---|---|
| Docker Compose local stack | Implemented | Starts PostgreSQL and the FastAPI backend, both bound to localhost by default. |
| Backend API | Implemented | FastAPI service with schema bootstrap on startup. |
| CSV statement ingestion | Implemented | Multipart upload with validation, file hashing, account scoping, and transaction dedupe. |
| Raw statement storage | Implemented | Files are stored on disk using content-addressed paths under the configured upload directory. |
| Statement purge | Implemented | Removes DB metadata and attempts to delete the stored file. |
| Categories and monthly budgets | Implemented | Category CRUD, budget upsert/list, budget status, and history-based suggestions. |
| Categorization rules | Implemented | Regex-based rules, retroactive apply option, manual correction, and rule proposal dry runs. |
| Recurring spend detection | Implemented | Deterministic monthly cadence detection from ledger transactions. |
| Frontend UI | Slice 1 shell + slices 10–13 UI | Authenticated shell with statements queue uploads, anomalies review, streaming chat, and transaction drill-down from anomaly links. Charts/budget editors remain PRD follow-ups. |
| Agent/chat workflows | Implemented | Embedded MCP-shaped read tools + deterministic streaming planner (`POST /chat/stream`). Aligns with GitHub slice 11 / issue #12. |
| PDF statement ingestion | Partial | Targeted parser scaffold at `pdf_cc.py`; synchronous auto-ingest still returns **501** when the parser reports ingest-ready rows. **Queued PDF jobs** (`POST /ingest/jobs/pdf`) record `needs_review` when confidence is low (GitHub slice 13 / issue #14). |

## Product direction

The intended product is a single-user, self-hosted finance application that runs locally by default. A user should be able to upload account statements, build a normalized ledger, manage categories and budgets, inspect recurring spending, and eventually ask an embedded AI agent questions such as why a month was expensive or which subscriptions are driving recurring costs.

The project is deliberately biased toward deterministic behavior:

| Design principle | What it means here |
|---|---|
| Ledger-first architecture | Analysis depends on normalized database records, not ad hoc prompt context. |
| Privacy by default | Services bind to `127.0.0.1` in local development unless you intentionally change that posture. |
| Deterministic before AI | Parsing, dedupe, budgeting, categorization rules, and recurring detection are implemented as code and SQL first. |
| Self-hosted workflow | Raw statement files and the database live on your machine. |
| Explainable system behavior | Unique constraints, regex rules, month-based budgets, and cadence checks are inspectable and testable. |

## Architecture overview

At the moment the architecture is intentionally small:

| Layer | Technology | Responsibility |
|---|---|---|
| Local orchestration | Docker Compose | Starts the database and backend with consistent environment wiring. |
| API service | FastAPI on Python 3.11+ | Exposes ingestion, budgeting, categorization, recurring, and health endpoints. |
| Frontend shell | Vite + React + TypeScript | Provides login, session-aware shell UI, and protected API smoke checks during local development. |
| Database | PostgreSQL 16 | System of record for institutions, accounts, statements, transactions, categories, budgets, and categorization rules. |
| File storage | Local filesystem bind mount | Stores uploaded raw statement files in a durable path outside the container image. |
| Packaging | `pyproject.toml` + setuptools | Installs the backend package and test dependencies. |
| Container runtime | Python 3.12 slim image | Runs the packaged backend behind Uvicorn in Docker. |

The future architecture described in the PRD adds a separate frontend, asynchronous ingestion jobs, analytics views, anomaly detection, and an embedded agent/tooling layer. That future direction matters because the current backend and schema are being built to support that system incrementally rather than as a throwaway prototype.

## Tech stack in detail

### Backend

The backend lives under [`backend/`](backend/) as a Python package named `pfa`.

| Component | Details |
|---|---|
| Framework | **FastAPI** for HTTP routing, request parsing, validation, and typed responses. |
| ASGI server | **Uvicorn** runs the app inside the container. |
| Database driver | **psycopg 3** is used for PostgreSQL access. |
| Multipart uploads | **python-multipart** handles CSV file uploads. |
| Testing | **pytest** plus **httpx/FastAPI TestClient** for integration-style API coverage. |
| Packaging | **setuptools** with a `pyproject.toml` configuration. |

### Data layer

PostgreSQL is the system of record and currently contains the core financial ledger model:

| Table | Purpose |
|---|---|
| `institutions` | Financial institutions such as banks or card issuers. |
| `accounts` | User accounts scoped to an institution and currency. |
| `statements` | Uploaded source files with account scoping, file hash, file path, and ingest counters. |
| `transactions` | Canonical ledger rows with dates, signed amounts, raw and normalized descriptions, dedupe fingerprint, and optional category. |
| `categories` | Budget and categorization labels with stable UUIDs and unique slugs. |
| `budgets` | Monthly envelope-style budget caps keyed by category and month. |
| `categorization_rules` | Deterministic regex rules ordered by priority. |

The schema is idempotent and is applied at API startup when `DATABASE_URL` is available. That makes local iteration easy while still keeping the schema under version control in [`backend/pfa/schema.sql`](backend/pfa/schema.sql).

### Infrastructure and storage

The local stack is defined in [`compose.yaml`](compose.yaml):

| Service | Details |
|---|---|
| `db` | PostgreSQL 16 Alpine image with a named volume `pgdata` for durable database storage. |
| `api` | Backend container built from [`backend/Dockerfile`](backend/Dockerfile), connected to the database through the internal Compose network. |

The API binds to `127.0.0.1:${API_PORT}` and Postgres binds to `127.0.0.1:${POSTGRES_PORT}` by default. Raw statements are stored via a bind mount, which defaults to `./data/raw-statements` on the host and `/data/raw-statements` inside the container.

## Implemented backend capabilities

### 1. CSV statement ingestion

The backend exposes `POST /ingest/csv` and accepts:

| Input | Notes |
|---|---|
| `account_id` | Required multipart form field; must reference an existing account. |
| `file` | Required CSV upload; maximum size is 10 MiB. |

Expected CSV columns today:

| Column | Required | Notes |
|---|---|---|
| `transaction_date` | Yes | Canonical transaction date. |
| `amount` | Yes | Signed numeric amount. |
| `description` | Yes | Source description text. |
| `posted_date` | No | Preserved when present. |
| `currency` | No | Defaults to `USD` if omitted. |

The ingestion flow is intentionally strict and deterministic:

1. The uploaded bytes are size-checked.
2. A SHA-256 hash is computed for the full statement file.
3. The CSV is parsed into normalized rows.
4. The account must already exist in the database.
5. An advisory lock is taken to prevent racing identical ingests for the same account and file hash.
6. The statement hash is checked for account-scoped idempotency.
7. The raw file is stored on disk using a content-addressed path.
8. The statement metadata is recorded in Postgres.
9. Transactions are inserted with deterministic dedupe fingerprints protected by a unique constraint.
10. Statement counters are updated with inserted and skipped-duplicate totals.

This gives the project two important safety properties:

| Safety property | How it works |
|---|---|
| Statement-level idempotency | `statements` has a unique constraint on `(account_id, sha256)`. Re-uploading the same file for the same account returns the prior statement result instead of reinserting rows. |
| Transaction-level dedupe | `transactions` has a unique constraint on `dedupe_fingerprint`, so overlapping statements can skip already-seen rows without corrupting the ledger. |

### 2. Raw statement file storage and purge

Uploaded statement bytes are persisted on disk, not just transiently held during request processing. The storage module uses SHA-256-based content addressing so each file lives at a deterministic path derived from its hash.

This is useful for future workflows such as:

- reprocessing derived data without asking the user to re-upload a file,
- auditing how a statement was ingested,
- supporting deletion and eventual retention policies.

The backend also exposes `DELETE /statements/{statement_id}`. That endpoint removes the database record and attempts to delete the stored file from disk. If the statement does not exist, the API returns `404`.

### 3. Categories and monthly envelope budgets

The budgeting layer is already implemented and uses a simple envelope-style monthly model:

| Endpoint group | Purpose |
|---|---|
| `POST /categories` and `GET /categories` | Create and list categories. |
| `PUT /budgets/{year_month}` | Upsert monthly budget amounts by category. |
| `GET /budgets/{year_month}` | List saved budget caps for a month. |
| `GET /budgets/{year_month}/status` | Compute month-to-date spend, projection, and remaining budget. |
| `POST /budgets/{year_month}/suggest` | Suggest budget amounts from historical spending across a configurable lookback window. |

Important budgeting behavior:

| Behavior | Details |
|---|---|
| Month key | Budgets are keyed by calendar month, represented internally as the first day of that month. |
| Budget values | Amounts must be non-negative. |
| Spend logic | Expenses are derived from transactions where `amount < 0`. |
| Projection model | The current implementation projects monthly spend linearly from the selected `as_of` date. |
| Suggestion model | Suggested amounts are based on historical totals averaged over the requested lookback window. |

Budget status becomes especially useful after transactions have been categorized because it links actual spending to budgeted categories through `transactions.category_id`.

### 4. Deterministic categorization rules

The backend already includes the beginnings of a rules-first categorization system:

| Endpoint | Purpose |
|---|---|
| `GET /categorization/rules` | List existing regex rules. |
| `POST /categorization/rules` | Create a new rule with category, regex pattern, priority, and optional retroactive application. |
| `DELETE /categorization/rules/{rule_id}` | Delete a rule. |
| `PUT /transactions/{transaction_id}/category` | Manually assign a category to a transaction. |
| `POST /transactions/{transaction_id}/rule-proposal` | Dry-run a possible rule and report how many uncategorized transactions it would affect. |

Key design choices:

| Choice | Why it matters |
|---|---|
| PostgreSQL regex validation | Patterns are validated against the same regex engine the database will use. |
| Priority ordering | Lower numeric priority wins when multiple rules match. |
| Optional retroactive application | A new rule can be applied immediately to matching historical rows. |
| Dry-run proposals | The system can show impact before a rule is persisted. |

This is important because categorization is one of the areas where a future LLM assistant can help, but the baseline workflow remains deterministic and inspectable.

### 5. Recurring spend detection

Recurring detection is implemented as a deterministic backend feature exposed at `GET /recurring`.

The current model looks for:

| Signal | Current rule |
|---|---|
| Transaction type | Expenses only (`amount < 0`). |
| Merchant grouping | Uses normalized descriptions. |
| Cadence | Monthly-like spacing with a tolerance window. |
| Minimum occurrences | Default is `3`, and the API enforces a lower bound of `3`. |
| Amount consistency | Similar amounts must stay within the allowed variance used by the detection logic. |

This is a good example of the project's philosophy: recurring-spend detection is implemented as transparent business logic now, and the future agent can explain or summarize the results later.

## API surface summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Redirect to the autogenerated API docs UI. |
| `POST` | `/auth/login` | Authenticate and create a session. |
| `POST` | `/auth/logout` | Revoke session and clear cookie. |
| `GET` | `/auth/session` | Return current session state. |
| `GET` | `/health` | Liveness endpoint for the API service. |
| `POST` | `/institutions` | Create an institution. |
| `GET` | `/institutions` | List institutions. |
| `POST` | `/accounts` | Create an account (requires existing institution). |
| `GET` | `/accounts` | List accounts. |
| `POST` | `/ingest/csv` | Upload and ingest a CSV statement for an existing account. |
| `POST` | `/ingest/jobs/csv` | Queue asynchronous CSV ingestion with step tracking (`extract → … → persist`). |
| `POST` | `/ingest/jobs/pdf` | Queue asynchronous PDF ingestion; low-confidence parses finish as `needs_review`. |
| `GET` | `/ingest/jobs` / `/ingest/jobs/{job_id}` | List ingest jobs or fetch one job plus step rows. |
| `DELETE` | `/statements/{statement_id}` | Purge a statement record and attempt to remove the stored file. |
| `POST` | `/categories` | Create a category. |
| `GET` | `/categories` | List categories. |
| `PUT` | `/budgets/{year_month}` | Upsert budget lines for a month. |
| `GET` | `/budgets/{year_month}` | List budgets for a month. |
| `GET` | `/budgets/{year_month}/status` | Return budget status metrics and projection. |
| `POST` | `/budgets/{year_month}/suggest` | Suggest budget amounts from history. |
| `GET` | `/categorization/rules` | List categorization rules. |
| `POST` | `/categorization/rules` | Create a categorization rule. |
| `DELETE` | `/categorization/rules/{rule_id}` | Delete a categorization rule. |
| `PUT` | `/transactions/{transaction_id}/category` | Manually categorize a transaction. |
| `POST` | `/transactions/{transaction_id}/rule-proposal` | Preview the impact of a possible rule. |
| `GET` | `/recurring` | Return recurring charge candidates. |
| `GET` | `/chat/tools` | List available agent tool definitions. |
| `POST` | `/chat/stream` | Stream agent responses via Server-Sent Events. |
| `POST` | `/ingest/pdf` | Upload and parse a credit card statement PDF (sync probe / future auto-ingest). |
| `GET` | `/anomalies` | Detect outliers in transaction data. |
| `GET` | `/transactions/{transaction_id}` | Fetch one ledger row for anomaly drill-down. |

### LangSmith tracing (optional)

Chat/tool invokes optionally wrap LangSmith `traceable` runs when tracing env vars are enabled.

| Step | What to do |
|---|---|
| Install extras | `python3 -m pip install -e ".[dev]"` pulls `langsmith` as an optional dependency. |
| Configure secrets locally | Copy [.env.example](.env.example) values into `.env`: `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, and optionally `LANGCHAIN_PROJECT`. Never commit keys. |
| Disable cleanly | Omit `LANGCHAIN_TRACING_V2` or set it to `false`; missing API keys simply skip tracing without crashing the API. |
| Verify | Ask the chat endpoint for a **ledger summary**, then confirm a corresponding tool span appears in the LangSmith UI for your project. |

### Agent tool surface (read-only MVP)

`/chat/tools` enumerates aggregates-first helpers (`ledger_summary`, `budget_status`, `cashflow_monthly`, `recurring_highlights`, `anomalies_summary`, `category_breakdown`) plus a fenced Markdown SQL block escape hatch (`SELECT`/`WITH` ending in `LIMIT n`, enforced server-side as `sql_select`). Mutating operations are intentionally absent from automatic invocation.

## Repository layout

| Path | Purpose |
|---|---|
| [`backend/`](backend/) | Python backend package, tests, and container build context. |
| [`backend/pfa/`](backend/pfa/) | Application code, schema SQL, and domain logic. |
| [`backend/tests/`](backend/tests/) | Unit and integration tests for parsing, ingestion, storage, budgeting, categorization, and recurring logic. |
| [`compose.yaml`](compose.yaml) | Local development stack definition. |
| [`.env.example`](.env.example) | Template for local environment variables. |
| [`scripts/verify-infra.sh`](scripts/verify-infra.sh) | Automated infrastructure verification for the Compose stack. |
| [`Makefile`](Makefile) | Convenience commands for infra verification and backend tests. |
| [`docs/PRD.md`](docs/PRD.md) | Product requirements and target architecture. |
| [`data/raw-statements/`](data/raw-statements/) | Default host-side storage directory for uploaded statements. |

## Local setup and run

### Prerequisites

You need Docker with Compose v2 for the default local workflow. For host-based development, use Python 3.11 or newer plus Node.js 20 or newer for the frontend shell.

### 1. Create your local environment file

```bash
cp .env.example .env
```

The `.env` file controls the database credentials, exposed host ports, raw statement storage path, and the single-user app-shell login. The defaults are set up for local-only development.

### 2. Create the raw statement storage directory

```bash
mkdir -p data/raw-statements
```

This directory is bind-mounted into the API container and is ignored by git.

### 3. Start the local stack

```bash
docker compose up -d
```

That starts:

- **`db`** on `127.0.0.1:${POSTGRES_PORT}`
- **`api`** on `127.0.0.1:${API_PORT}`
- **`frontend`** (Vite dev server) on `127.0.0.1:${FRONTEND_PORT}` — proxies `/api/*` to the API container (`API_PROXY_TARGET`).

The API waits for the database to become healthy before starting. On startup, the backend applies the schema automatically if `DATABASE_URL` is configured.

If you open the API host in a browser at `http://127.0.0.1:${API_PORT}`, it redirects to the FastAPI docs UI at `/docs`.

### 4. Verify infrastructure wiring

```bash
make verify-infra
```

This script validates the Compose configuration, checks database readiness, confirms connectivity, verifies that the published port matches `POSTGRES_PORT`, confirms data survives a container restart, and checks that the raw-statement bind mount exists.

### 5. Run the backend directly on the host (optional)

If you prefer to run the API outside Docker while still using the Compose database:

```bash
cd backend
python3 -m pip install -e ".[dev]"
uvicorn pfa.main:app --reload
```

With the default `.env.example`, the backend connects to PostgreSQL through `DATABASE_URL=postgresql://pfa:pfa_dev_password_change_me@127.0.0.1:5432/pfa`.

### 6. Run the frontend app shell (optional, recommended for slice 1)

If **step 3** already started the **`frontend`** container, open `http://127.0.0.1:${FRONTEND_PORT:-5173}` and skip the commands below. Otherwise, from another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` and sign in with `PFA_AUTH_USERNAME` / `PFA_AUTH_PASSWORD` from `.env`. The Vite dev server proxies `/api/*` requests to `http://127.0.0.1:8000`, so the browser can keep the session cookie while talking to protected backend routes.

**Frontend source layout (`frontend/src/`):**

| Area | Purpose |
|------|---------|
| `app/` | Login form (`app/auth`) and authenticated shell + routes (`app/layout`). |
| `features/<name>/` | Route-level screens (for example `features/statements`, `features/transactions`). |
| `api/` | HTTP helpers (`http.ts`) and domain modules re-exported from `api/index.ts`; feature code imports via the `@/api` alias. |
| `styles/` | Global CSS partials; `styles/index.css` pulls in shell styling and feature chunks. |

### 7. Stop the stack

```bash
docker compose down
```

To remove the PostgreSQL named volume as well:

```bash
docker compose down -v
```

## Testing

The repository now includes both backend and frontend validation paths.

| Test area | Coverage |
|---|---|
| CSV parsing | Required columns, normalization, and parse errors. |
| Dedupe logic | Fingerprint behavior and duplicate handling. |
| File storage | Hash generation, content-addressed storage, and file deletion behavior. |
| Ingestion HTTP flow | Upload validation, idempotency, unknown-account handling, and purge behavior. |
| Budgeting | Category creation, budget upsert/list, projections, and suggestions. |
| Categorization | Regex validation, priority ordering, retroactive apply, manual correction, and dry-run proposals. |
| Recurring detection | Pure recurrence logic and API behavior. |
| Authentication | Login, logout, session bootstrap, and protected-route enforcement. |

The frontend app-shell tests cover:

| Test area | Coverage |
|---|---|
| Session bootstrap | Unauthenticated load renders the login form. |
| Login flow | Successful login renders the authenticated shell and reaches a protected API path. |

Run the backend tests with a live PostgreSQL database reachable at `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql://pfa:pfa_dev_password_change_me@127.0.0.1:5432/pfa
make test-backend
```

Integration tests are skipped automatically when `DATABASE_URL` is not set.

Run the frontend tests, build, and lint from `frontend/`:

```bash
npm run test
npm run build
npm run lint
```

## Security and privacy posture

This project is intentionally conservative in local development:

| Posture | Current behavior |
|---|---|
| Network exposure | Compose binds the API and Postgres to `127.0.0.1` by default. |
| Data ownership | Raw statements and the database live on local storage you control. |
| Deterministic processing | Core ingestion and ledger behavior does not depend on an external AI provider. |
| Future agent safety | The PRD specifies confirm-before-write behavior and aggregate-first model context. |

This does not make the project production-ready by itself. If you later expose it beyond localhost, you will need to add the usual operational controls such as TLS termination, authentication hardening, backup strategy, and stricter request-surface protections.

## Roadmap and planned work

The implemented backend is the foundation for a broader product. The PRD calls out several next layers:

| Planned area | Status | Summary |
|---|---|---|
| Authentication and app shell | Implemented | Login, session management, and protected-route enforcement. |
| Async jobs and job status | Implemented | Durable ingestion jobs with step-level progress, background processing, and retry support. |
| Frontend application | Partial | Authenticated shell plus statements queue uploads, anomalies list/detail navigation, streaming chat, and transaction drill-down are implemented; richer budgeting/charts pages remain PRD follow-ups. |
| PDF ingestion | Partial | Parser scaffold + confidence/HITL gate at `backend/pfa/pdf_cc.py`. Queued PDF jobs finish as `needs_review` when confidence is low; synchronous auto-ingest still returns **501** once the parser reports ingest-ready rows. |
| Agent and tool layer | Implemented | MCP-shaped **read-only** tools (aggregates + guarded `sql_select`) and deterministic streaming chat are live; mutating agent actions stay unimplemented pending confirmation UX. |
| Observability | Implemented | LangSmith tracing wired for agent and tool execution. |
| More analytics | Implemented | Row and series outlier detection API is live. |

## Disclaimer

This project is a tool for organizing and analyzing your own financial data. It is not financial, legal, or tax advice. You are responsible for securing your machine, protecting backups, and safeguarding any credentials or API keys you use with the system.
