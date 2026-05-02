-- Ledger schema (slices 4–6). Idempotent: safe to apply on every API startup.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS auth_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at
  ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS institutions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  institution_id UUID NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Slice 4: durable async ingest job queue.
CREATE TABLE IF NOT EXISTS ingest_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  statement_id UUID,
  filename TEXT NOT NULL,
  file_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  parsed_rows INTEGER,
  inserted_rows INTEGER,
  skipped_duplicates INTEGER,
  error_detail TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status_created_at
  ON ingest_jobs(status, created_at DESC);

-- Idempotent column addition: ensures DBs provisioned before this column was
-- added to the CREATE TABLE above receive it on next schema migration run.
ALTER TABLE ingest_jobs
  ADD COLUMN IF NOT EXISTS statement_id UUID;

CREATE TABLE IF NOT EXISTS ingest_job_steps (
  job_id UUID NOT NULL REFERENCES ingest_jobs(id) ON DELETE CASCADE,
  step_key TEXT NOT NULL,
  status TEXT NOT NULL,
  item_count INTEGER,
  detail TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  PRIMARY KEY (job_id, step_key)
);

-- Slice 5: raw file storage with hash-level idempotency.
CREATE TABLE IF NOT EXISTS statements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  file_path TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  inserted INTEGER NOT NULL DEFAULT 0,
  skipped_duplicates INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT statements_account_sha256_key UNIQUE (account_id, sha256)
);

CREATE TABLE IF NOT EXISTS transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  transaction_date DATE NOT NULL,
  posted_date DATE,
  amount NUMERIC(18, 4) NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  description_raw TEXT NOT NULL,
  description_normalized TEXT NOT NULL,
  dedupe_fingerprint TEXT NOT NULL,
  source_statement_id UUID REFERENCES statements(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT transactions_dedupe_fingerprint_key UNIQUE (dedupe_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_date
  ON transactions(account_id, transaction_date);

-- Slice 6: categories + envelope budgets (+ optional categorization on transactions).
CREATE TABLE IF NOT EXISTS categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS budgets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  month DATE NOT NULL,
  amount NUMERIC(18, 4) NOT NULL CHECK (amount >= 0),
  currency TEXT NOT NULL DEFAULT 'USD',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (category_id, month)
);

CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month);

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES categories(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_category_date ON transactions(category_id, transaction_date);

-- Slice 7: deterministic categorization rules.
CREATE TABLE IF NOT EXISTS categorization_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  pattern TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cat_rules_priority ON categorization_rules(priority);
