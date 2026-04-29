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
- Acceptance: Insert 1000 transactions; query by date range returns correct subset in <100ms

### R2 — Statement Metadata Schema
Tracks ingested statement files to prevent duplicate ingestion.
- Fields: `id` (UUID PK), `filename` (text), `source_bank` (enum), `file_hash` (text unique), `period_start` (date), `period_end` (date), `transaction_count` (int), `ingested_at` (timestamptz), `status` (enum: processing/complete/failed), `error_message` (text nullable)
- Acceptance: Re-uploading same file detectable via `file_hash` lookup

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
- `insert_transactions(statement_id, transactions: List[Transaction]) → int` (returns count)
- Acceptance: Each function returns correct typed results; invalid inputs raise typed exceptions

## Cross-References
- ingestion: writes via `insert_transactions`
- analytics: reads via `get_transactions`, `get_monthly_totals`
- infra: Postgres container and `DATABASE_URL` env var
