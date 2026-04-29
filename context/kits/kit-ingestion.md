---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: ingestion
status: Draft
---

# Kit: Ingestion

HTTP upload endpoint accepting PDF or CSV bank statements, parsing them into normalized transactions, and writing to storage. Supports Chase, Amex, Capital One, and Robinhood.

## Requirements

### R1 — Upload Endpoint
Server exposes an authenticated file upload endpoint.
- `POST /upload` accepts `multipart/form-data` with a single file field (`file`)
- Optional form field `bank` hints the source bank (values: chase, amex, capital_one, robinhood); if omitted, bank is auto-detected
- Returns JSON: `{ statement_id, bank_detected, transaction_count, period_start, period_end }`
- Returns 400 if file type not PDF or CSV
- Returns 409 if identical file already ingested (detected via SHA-256 hash)
- Acceptance: Upload Chase CSV → response contains correct bank, count, period

### R2 — Bank Auto-Detection
When `bank` field omitted, parser infers source bank from file content.
- CSV files: detected by examining header row for bank-specific column names
- PDF files: detected by examining first page text for bank name / logo text
- Detection is best-effort; falls back to requiring explicit `bank` field if ambiguous
- Acceptance: Upload Chase CSV without `bank` field → detected as `chase`

### R3 — Chase Parser
Parses Chase bank/credit card CSV exports.
- Handles both checking and credit card CSV formats (column sets differ)
- Columns mapped: Transaction Date → `date`, Description → `description` + `merchant`, Amount → `amount` (negative = debit), Category → `category`
- Skips header row; handles empty rows gracefully
- Acceptance: Parse sample Chase CSV → all transactions extracted with correct signs and dates

### R4 — Amex Parser
Parses American Express PDF and CSV statement exports.
- CSV format: Date, Description, Amount (negative = charge)
- PDF format: tabular extraction from statement pages
- Merchant name extracted from description field
- Acceptance: Parse sample Amex statement → transactions match manual count from statement

### R5 — Capital One Parser
Parses Capital One CSV statement exports.
- Columns: Transaction Date, Posted Date, Card No., Description, Category, Debit, Credit
- Debit/Credit are separate columns (one populated, one empty per row)
- `amount` = Credit - Debit (positive = credit to account)
- Acceptance: Parse sample CapOne CSV → debits are negative, credits are positive

### R6 — Robinhood Parser
Parses Robinhood CSV account activity exports.
- CSV only (no PDF support for Robinhood)
- Columns: Activity Date, Process Date, Settle Date, Instrument, Description, Trans Code, Quantity, Price, Amount
- Filter to cash transactions only (deposits, withdrawals, dividends); skip equity trades
- `transaction_type` = credit for deposits/dividends, debit for withdrawals
- Acceptance: Parse sample Robinhood CSV → only cash-flow rows present, equity trades excluded

### R7 — Transaction Normalization
All parsed transactions converted to canonical schema before storage.
- Date normalized to ISO 8601 date
- Amount normalized to positive number; `transaction_type` encodes direction
- Description cleaned: leading/trailing whitespace stripped; control characters removed
- Merchant extracted from description using simple heuristics (first token before delimiter)
- Duplicate detection within single upload: same date + amount + description → deduplicated
- Acceptance: Two identical rows in one CSV → only one transaction stored

### R8 — Deduplication Across Uploads
Transactions from re-uploaded or overlapping statements not duplicated in storage.
- File-level dedup via SHA-256 hash (R1)
- Row-level dedup: transaction with same `source_bank` + `date` + `amount` + `raw_description` already in DB → skipped
- Dedup stats returned in upload response: `{ duplicates_skipped }`
- Acceptance: Upload same statement twice → second upload returns 409; upload overlapping statements → overlapping transactions not duplicated

## Cross-References
- storage: writes via `insert_transactions`; reads `get_statement_by_hash` for dedup
- auth: upload endpoint protected by bearer token middleware
- observability: upload traces to LangSmith; request logged with `request_id`
- infra: no special infra needs beyond app container
