---
created: "2026-04-28"
last_edited: "2026-04-28"
---
# Implementation Tracking: storage

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-011 | DONE | Alembic init; env.py reads DATABASE_URL, converts asyncpg→psycopg2 for sync migrations |
| T-012 | DONE | db.py: SQLAlchemy async engine, pool_size=5/max_overflow=10 configurable via env, async_sessionmaker context manager |
| T-013 | DONE | docker-compose app service runs `alembic upgrade head` before uvicorn |
| T-014 | DONE | Migration 001: source_bank, transaction_type, statement_status enums |
| T-015 | DONE | Migration 002: statements table (id UUID PK, file_hash UNIQUE constraint) |
| T-016 | DONE | Migration 003: transactions table (full schema, raw_description_hash char(64), 4 indexes) |
| T-017 | DONE | Migration 004: UNIQUE (source_bank, date, amount, raw_description_hash) on transactions |
| T-018 | DONE | Migration 005: sessions table (id UUID PK, user_email, created_at, expires_at, index on expires_at) |
| T-019 | DONE | test_date_range_query_under_100ms: 1000 tx insert + Jan query < 100ms PASS |
| T-020 | DONE | test_concurrent_file_hash_unique: parallel inserts → exactly 1 ok, 1 conflict PASS |
| T-021 | DONE | test_migrate_up_idempotent + tables_exist PASS |
| T-022 | DONE | test_pool_50_concurrent: 50 asyncio.gather queries without exhaustion PASS |
| T-023 | DONE | models.py: Transaction, Statement, UserSession ORM classes (SQLAlchemy 2.0 Mapped annotations) |
| T-024 | DONE | queries.get_transactions() + get_transactions_by_merchant() with date/bank/category/merchant filters |
| T-025 | DONE | queries.get_monthly_totals(year, month) → Dict[category, Decimal], debit-only aggregation |
| T-026 | DONE | queries.get_statement_by_hash(file_hash) → Statement|None |
| T-027 | DONE | queries.insert_transactions() ON CONFLICT DO NOTHING, returns (attempted, inserted) |
| T-028 | DONE | queries.insert_statement_and_transactions() atomic pg_insert with RETURNING, None on duplicate |
| T-029 | DONE | 11 typed exception + concurrent insert tests — 11/11 PASS |
| T-030 | DONE | 3 session schema tests (unexpired/expired/unknown) — 3/3 PASS |
