# PDF ingest categorization and transaction source column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When PDF-derived rows are persisted, assign each new transaction’s `category_id` **before** insert when possible: first match existing **categorization rules** against the normalized description (no LLM); if no rule matches and `OPENROUTER_API_KEY` is set, call **OpenRouter** via existing `suggest_category_slug` and only persist if the slug validates against the catalog. Separately, expose each ledger row’s **import source** (statement filename) on `GET /transactions` and in the Transactions UI.

**Architecture:** Extend `ingest_rows` with a boolean `llm_if_unmatched` used only on PDF code paths (`POST /ingest/pdf`, `process_pdf_job` success branch). Rule matching is lifted into a read-only helper mirroring `apply_rules` SQL so we can resolve `category_id` **without** an inserted row. CSV paths keep `llm_if_unmatched=False` but still benefit from rule-first `category_id` on insert (same helper, no LLM). Listing joins `transactions.source_statement_id` → `statements.filename`.

**Tech Stack:** PostgreSQL, FastAPI, existing `pfa.llm_category_suggest`, React/Vite frontend.

---

## File structure

| Path | Change |
|------|--------|
| `backend/pfa/categorization.py` | Add `category_id_from_rules(conn, description_normalized: str) -> str \| None`. |
| `backend/pfa/ingest.py` | Add `resolve_initial_category_id(...)`, extend `ingest_rows(..., llm_if_unmatched: bool = False)`, include `category_id` in `INSERT` when resolved. |
| `backend/pfa/main.py` | `ingest_pdf`: pass `llm_if_unmatched=True`; `ingest_csv`: pass `False` (explicit). |
| `backend/pfa/ingest_jobs.py` | `process_pdf_job` success path: `llm_if_unmatched=True`; `process_csv_job`: `False`. |
| `backend/pfa/categorization_api.py` | `TransactionListItem.source_statement_filename`; extend list SQL + count SQL with `LEFT JOIN statements`. |
| `backend/tests/test_categorization_http.py` | Assert list JSON includes `source_statement_filename` (integration). |
| `backend/tests/test_ingest_category_resolution.py` | **Create** — unit tests for rule helper + `ingest_rows` with mocked LLM (no Postgres optional: use monkeypatch + integration when `DATABASE_URL` set). |
| `frontend/src/api/transactions.ts` | `Transaction` type + list typing. |
| `frontend/src/features/transactions/TransactionsPage.tsx` | Table column **Source**, row cell, expand `colSpan`. |
| `frontend/src/styles/features/transactions-page.css` | Narrow column / ellipsis for long filenames. |

---

### Self-review

| Requirement | Task |
|-------------|------|
| PDF: category before DB from rules or LLM | Tasks 1–4 |
| Display source on transactions | Tasks 5–7 |
| Spec placeholders | None |
| Type names consistent | `source_statement_filename` everywhere |

---

### Task 1: Rule lookup without an existing transaction row

**Files:**
- Modify: `backend/pfa/categorization.py`
- Test: `backend/tests/test_ingest_category_resolution.py` (create)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_ingest_category_resolution.py`:

```python
"""Unit tests for category_id_from_rules (no DB required if skipped)."""

from uuid import uuid4

import pytest

from pfa.categorization import category_id_from_rules


@pytest.mark.integration
def test_category_id_from_rules_matches_priority(database_url):
    import psycopg
    from pfa.db import ensure_schema

    conn = psycopg.connect(database_url)
    ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE categorization_rules, categories RESTART IDENTITY CASCADE")
        cid = uuid4()
        cur.execute(
            "INSERT INTO categories (id, slug, name) VALUES (%s, %s, %s)",
            (str(cid), "food", "Food"),
        )
        cur.execute(
            """INSERT INTO categorization_rules (category_id, pattern, priority)
               VALUES (%s, %s, %s)""",
            (str(cid), "starbucks", 10),
        )
    conn.commit()

    got = category_id_from_rules(conn, "STARBUCKS SEATTLE WA")
    conn.close()
    assert got == str(cid)
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd backend && DATABASE_URL=postgresql://... uv run pytest tests/test_ingest_category_resolution.py::test_category_id_from_rules_matches_priority -v`

Expected: FAIL — `category_id_from_rules` not defined.

- [ ] **Step 3: Implement helper**

Append to `backend/pfa/categorization.py`:

```python
def category_id_from_rules(conn: psycopg.Connection, description_normalized: str) -> str | None:
    """Return first matching rule category_id for this description, or None."""
    row = conn.execute(
        """
        SELECT r.category_id
        FROM categorization_rules r
        WHERE %s ~* r.pattern
        ORDER BY r.priority ASC, r.created_at ASC
        LIMIT 1
        """,
        (description_normalized,),
    ).fetchone()
    return str(row[0]) if row else None
```

- [ ] **Step 4: Re-run test**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pfa/categorization.py backend/tests/test_ingest_category_resolution.py
git commit -m "feat(categorization): resolve category from rules by description"
```

---

### Task 2: Resolve initial category (rules + optional LLM)

**Files:**
- Modify: `backend/pfa/ingest.py`

- [ ] **Step 1: Add imports and resolver**

At top of `ingest.py`, add:

```python
from pfa.budget_service import list_categories
from pfa.categorization import apply_rules, category_id_from_rules
from pfa.llm_category_suggest import suggest_category_slug
```

Add function **before** `ingest_rows`:

```python
def resolve_initial_category_id(
    conn: psycopg.Connection,
    *,
    description_raw: str,
    description_normalized: str,
    llm_if_unmatched: bool,
) -> str | None:
    rid = category_id_from_rules(conn, description_normalized)
    if rid is not None:
        return rid
    if not llm_if_unmatched:
        return None
    cats = list_categories(conn)
    slug, err = suggest_category_slug(
        description_raw=description_raw,
        description_normalized=description_normalized,
        categories=cats,
    )
    if err or not slug:
        return None
    for c in cats:
        if c["slug"] == slug:
            return str(c["id"])
    return None
```

- [ ] **Step 2: Extend `ingest_rows` signature**

Change def line to:

```python
def ingest_rows(
    conn: psycopg.Connection,
    account_id: UUID,
    rows: list[ParsedCsvRow],
    source_statement_id: UUID | None = None,
    *,
    llm_if_unmatched: bool = False,
) -> tuple[int, int]:
```

- [ ] **Step 3: Inside the loop, after `desc_norm = ...`, resolve category**

```python
            cat_id = resolve_initial_category_id(
                conn,
                description_raw=row.description_raw,
                description_normalized=desc_norm,
                llm_if_unmatched=llm_if_unmatched,
            )
```

- [ ] **Step 4: Change INSERT to include optional category_id**

Replace the INSERT block with:

```python
            result = cur.execute(
                """
                INSERT INTO transactions (
                  account_id, transaction_date, posted_date, amount, currency,
                  description_raw, description_normalized, dedupe_fingerprint,
                  source_statement_id, category_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dedupe_fingerprint) DO NOTHING
                RETURNING id
                """,
                (
                    str(account_id),
                    row.transaction_date,
                    row.posted_date,
                    row.amount,
                    row.currency,
                    row.description_raw,
                    desc_norm,
                    fp,
                    str(source_statement_id) if source_statement_id else None,
                    cat_id,
                ),
            ).fetchone()
```

- [ ] **Step 5: Keep `apply_rules` after successful insert** (still fills gaps when `category_id` was NULL)

No code removal — existing `apply_rules(conn, str(result[0]))` stays.

- [ ] **Step 6: Commit**

```bash
git add backend/pfa/ingest.py
git commit -m "feat(ingest): resolve category at insert (rules + optional LLM for PDF)"
```

---

### Task 3: Wire PDF paths only for LLM fallback

**Files:**
- Modify: `backend/pfa/main.py`
- Modify: `backend/pfa/ingest_jobs.py`

- [ ] **Step 1: `main.py` — CSV explicit False, PDF True**

Replace CSV `ingest_rows` call:

```python
        inserted, skipped = ingest_rows(
            conn, account_id, rows, source_statement_id=stmt_id, llm_if_unmatched=False
        )
```

Replace PDF `ingest_rows` call:

```python
        inserted, skipped = ingest_rows(
            conn, account_id, rows, source_statement_id=stmt_id, llm_if_unmatched=True
        )
```

- [ ] **Step 2: `ingest_jobs.py` — CSV job**

Change CSV branch `ingest_rows` (around line 256) to:

```python
            inserted, skipped = ingest_rows(
                conn,
                account_id,
                rows,
                source_statement_id=statement_id,
                llm_if_unmatched=False,
            )
```

- [ ] **Step 3: `ingest_jobs.py` — PDF job success path**

Change PDF branch `ingest_rows` (around line 443) to:

```python
            inserted, skipped = ingest_rows(
                conn,
                account_id,
                rows,
                source_statement_id=statement_id,
                llm_if_unmatched=True,
            )
```

- [ ] **Step 4: Optional — update step detail strings** for PDF categorize step to `"rules + optional OpenRouter at insert"` (cosmetic).

- [ ] **Step 5: Commit**

```bash
git add backend/pfa/main.py backend/pfa/ingest_jobs.py
git commit -m "feat(ingest): enable LLM category fallback on PDF ingest paths only"
```

---

### Task 4: List API — statement filename as source

**Files:**
- Modify: `backend/pfa/categorization_api.py`
- Modify: `backend/tests/test_categorization_http.py`

- [ ] **Step 1: Extend model**

In `TransactionListItem`, add:

```python
    source_statement_filename: str | None
```

- [ ] **Step 2: Update `count_sql` and `data_sql` in `list_transactions`**

Add join:

```sql
LEFT JOIN statements s ON s.id = t.source_statement_id
```

Extend SELECT list for data rows:

```sql
..., t.category_id, c.name AS category_name, t.created_at,
       s.filename AS source_statement_filename
```

Ensure `WHERE` still prefixes `t.` / joins correctly.

- [ ] **Step 3: Map rows** — dict_row keys include `source_statement_filename`.

- [ ] **Step 4: Integration assertion**

After `_ingest` in `test_list_transactions_after_ingest`, add:

```python
    assert rows[0]["source_statement_filename"] == "t.csv"
```
(Adjust filename if fixture uses different mock name — match `_CSV` upload name in test helper.)

- [ ] **Step 5: Run integration tests** with `DATABASE_URL` set.

Run: `cd backend && DATABASE_URL=... uv run pytest tests/test_categorization_http.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/pfa/categorization_api.py backend/tests/test_categorization_http.py
git commit -m "feat(api): include source statement filename on transaction list"
```

---

### Task 5: Frontend — Source column

**Files:**
- Modify: `frontend/src/api/transactions.ts`
- Modify: `frontend/src/features/transactions/TransactionsPage.tsx`
- Modify: `frontend/src/styles/features/transactions-page.css`
- Modify: `frontend/src/features/transactions/TransactionsPage.test.tsx` if present

- [ ] **Step 1: Extend type**

In `transactions.ts`:

```typescript
export type Transaction = {
  id: string
  account_id: string
  transaction_date: string
  amount: string
  description_raw: string
  description_normalized: string
  category_id: string | null
  category_name: string | null
  source_statement_filename: string | null
  created_at: string
}
```

- [ ] **Step 2: Table header** — add `<th scope="col" className="txn-th txn-th-source">Source</th>` after Category (non-sortable for MVP).

- [ ] **Step 3: Row cells** — in main row `<tr>`, add:

```tsx
        <td className="txn-source" title={tx.source_statement_filename ?? undefined}>
          {tx.source_statement_filename ?? '—'}
        </td>
```

- [ ] **Step 4: Expand row `colSpan`** — change `colSpan={4}` to `colSpan={5}` on the detail row.

- [ ] **Step 5: CSS**

```css
.txn-source {
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.88rem;
  color: #94a3b8;
}
```

- [ ] **Step 6: Run frontend tests**

Run: `cd frontend && npm test -- --run`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/transactions.ts frontend/src/features/transactions/TransactionsPage.tsx frontend/src/styles/features/transactions-page.css
git commit -m "feat(ui): show transaction import source filename"
```

---

### Task 6: Performance / ops note (no code)

- [ ] Document in commit message or README snippet: **large PDFs** may trigger **one OpenRouter request per inserted row** when rules do not match; follow-up could batch prompts into a single completion.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-03-pdf-ingest-category-and-transaction-source.md`.

**Two execution options:**

1. **Subagent-driven (recommended)** — **sub-skill:** superpowers:subagent-driven-development  
2. **Inline execution** — **sub-skill:** superpowers:executing-plans  

Which approach?
