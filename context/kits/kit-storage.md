---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: storage
status: Draft
---

# Kit: Storage

Postgres schema and migration layer for normalized financial transactions and statement metadata.

## Requirements

### R1 — Transaction Schema
Core table stores normalized transactions from all bank sources.
- Fields: `id` (UUID PK), `statement_id` (FK), `date` (date), `description` (text), `amount` (numeric 12,2), `currency` (char 3, default USD), `category` (text nullable), `merchant` (text nullable), `source_bank` (enum), `transaction_type` (enum: debit/credit), `raw_description` (text), `created_at` (timestamptz)
- `source_bank` enum values: chase, amex, capital_one, robinhood
- Indexes: `date`, `source_bank`, `category`, `merchant`
- Add field: `raw_description_hash` (char 64) — SHA-256 hex digest of `raw_description`, computed on insert. Avoids index size limits on long text columns.
- DB-level unique constraint: `UNIQUE (source_bank, date, amount, raw_description_hash)` — enforced by Postgres, not application logic
- Acceptance: Insert 1000 transactions; query by date range returns correct subset in <100ms
- Acceptance: Attempting to insert a transaction with same source_bank + date + amount + raw_description_hash as existing row is rejected at DB level (ON CONFLICT)

### R2 — Statement Metadata Schema
Tracks ingested statement files to prevent duplicate ingestion.
- Fields: `id` (UUID PK), `filename` (text), `source_bank` (enum), `file_hash` (text unique), `period_start` (date), `period_end` (date), `transaction_count` (int), `ingested_at` (timestamptz), `status` (enum: processing/complete/failed), `error_message` (text nullable)
- `file_hash` column has a DB-level `UNIQUE` constraint (not just application-level assertion)
- Acceptance: Re-uploading same file detectable via `file_hash` lookup
- Acceptance: Two concurrent inserts of statements with same file_hash → exactly one succeeds; other receives unique constraint violation

### R3 — Migration Management
Schema changes managed via versioned migrations.
- Each schema change has a corresponding migration file
- Migrations are applied in order; rollback supported
- Migration state tracked in DB (not just filesystem)
- Acceptance: `migrate up` on empty DB produces correct schema; `migrate up` on current DB is a no-op

### R4 — Connection Management
Database connections managed efficiently under concurrent load.
- Connection pool with configurable min/max size
- Connections released promptly after each operation
- `DATABASE_URL` read from environment
- Acceptance: 50 concurrent requests complete without connection exhaustion or timeout

### R5 — Query Interface
Typed query functions for analytics domain consumption.
- `get_transactions(start_date, end_date, bank=None, category=None) → List[Transaction]`
- `get_transactions_by_merchant(merchant, start_date, end_date) → List[Transaction]`
- `get_monthly_totals(year, month) → Dict[category, Decimal]`
- `get_statement_by_hash(file_hash) → Statement | None`
- `insert_transactions(statement_id, transactions: List[Transaction]) → Tuple[int, int]` (returns `(attempted, inserted)` — inserted count reflects actual rows written; attempted − inserted = duplicates skipped)
- `insert_statement_and_transactions(statement: Statement, transactions: List[Transaction]) → Tuple[int, int] | None` — atomic operation: inserts statement keyed on `file_hash`; if statement already exists returns `None` (caller should respond 409); otherwise inserts transactions with deduplication and returns `(attempted, inserted)`. Entire operation is a single DB transaction.
- Acceptance: Each function returns correct typed results; invalid inputs raise typed exceptions; calling `insert_statement_and_transactions` concurrently with same file_hash → exactly one call returns counts, other returns None

### R6 — Session Schema
Server-side authentication sessions persisted in Postgres for stateless server processes.
- `sessions` table stores server-side auth sessions
- Fields: `id` (UUID PK), `user_email` (text NOT NULL), `created_at` (timestamptz NOT NULL), `expires_at` (timestamptz NOT NULL)
- Index on `expires_at` for efficient expired session cleanup
- Auth middleware queries: `SELECT id FROM sessions WHERE id = $1 AND expires_at > now()`
- Acceptance: Insert session row; query with valid id and unexpired time returns row; query with expired time or unknown id returns no rows

## Cross-References
- ingestion: writes via `insert_transactions`
- analytics: reads via `get_transactions`, `get_monthly_totals`
- auth: sessions table (R6) used by auth middleware for session validation and logout
- infra: Postgres container and `DATABASE_URL` env var
