# OpenRouter category suggestions, default categories, and Statements UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional AI-assisted category suggestions via OpenRouter for ledger transactions, seed a sensible default category set for manual correction workflows, improve Statements page layout and clarity, and collapse the “add bank / account” panel until the user explicitly expands it (except first-time onboarding when no accounts exist).

**Architecture:** Backend owns all LLM calls: read `OPENROUTER_API_KEY` and model from env, call OpenRouter’s OpenAI-compatible `chat/completions` API with a strict JSON-only system prompt that constrains output to **existing** category slugs from the database (no invented categories). New authenticated endpoint returns a suggestion plus metadata; the UI never sends the API key. Default categories are inserted idempotently in `schema.sql` (same pattern as `account_types`). Statements page uses a native `<details>`/`<summary>` (or a small React state toggle) so the add-account form is **closed by default** whenever at least one account already exists, and **open by default** only when there are zero accounts.

**Tech Stack:** FastAPI, Pydantic v2, `httpx` (sync client), PostgreSQL; React + TypeScript + CSS already in repo.

---

## File structure (creates / modifies)

| Path | Responsibility |
|------|----------------|
| `backend/pyproject.toml` | Add runtime dependency `httpx` (used for OpenRouter HTTP). |
| `.env.example` | Document `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, optional `OPENROUTER_HTTP_REFERER`. |
| `backend/pfa/llm_category_suggest.py` | **Create** — build prompt, call OpenRouter, parse JSON, validate `category_slug` against DB. |
| `backend/pfa/categorization_api.py` | New route e.g. `POST /transactions/{transaction_id}/suggest-category` returning suggestion DTO. |
| `backend/pfa/schema.sql` | Seed `INSERT INTO categories ... ON CONFLICT (slug) DO NOTHING` for human-correction staples. |
| `backend/tests/test_llm_category_suggest.py` | **Create** — unit tests with `httpx` mocked (no real network). |
| `backend/tests/test_categorization_http.py` | Integration test for new endpoint (mock OpenRouter via `monkeypatch` on suggest function). |
| `frontend/src/api/transactions.ts` | `suggestTransactionCategory(txId: string)` calling new endpoint. |
| `frontend/src/features/transactions/TransactionsPage.tsx` | Optional “Suggest category” control next to manual category flow (calls API, pre-fills select). |
| `frontend/src/features/statements/StatementsPage.tsx` | Collapsible add-account section; layout tweaks. |
| `frontend/src/styles/features/statements-queue.css` | Polish for Statements sections / summary button. |

---

### Self-review

**Spec coverage**

| Requirement | Task |
|-------------|------|
| LLM via OpenRouter for category identification | Tasks 1–3, 5–6 |
| Categories for human correction (defaults) | Task 4 |
| Statements page better looking / intuitive | Tasks 7–8 |
| Add-bank/account UI collapsed until “Add account” clicked | Task 7 |

**Placeholder scan:** None.

**Type consistency:** Suggestion response uses `category_id` (UUID) resolved from validated slug.

---

### Task 1: Dependencies and environment

**Files:**

- Modify: `backend/pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add httpx to main dependencies**

In `[project] dependencies`, add:

```toml
  "httpx>=0.27",
```

- [ ] **Step 2: Document env vars in `.env.example`**

Append:

```bash
# Optional — OpenRouter for AI category suggestions (POST .../suggest-category).
# OPENROUTER_API_KEY=
# OPENROUTER_MODEL=openai/gpt-4o-mini
# OPENROUTER_HTTP_REFERER=https://localhost  # optional site URL for OpenRouter rankings
```

- [ ] **Step 3: Install and commit**

Run: `cd backend && uv sync`

Run: `git add backend/pyproject.toml backend/uv.lock .env.example && git commit -m "chore: httpx + OpenRouter env template"`

---

### Task 2: Core LLM suggestion module (OpenRouter)

**Files:**

- Create: `backend/pfa/llm_category_suggest.py`

- [ ] **Step 1: Implement suggester with validation**

```python
"""OpenRouter-backed category suggestion constrained to existing categories."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def suggest_category_slug(
    *,
    description_normalized: str,
    description_raw: str,
    categories: list[dict[str, Any]],
    timeout_sec: float = 30.0,
) -> tuple[str | None, str | None]:
    """Returns (matched_slug_or_none, error_message_or_none).

    categories: rows with keys id, slug, name (slug unique).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None, "OPENROUTER_API_KEY is not set"

    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
    slug_set = {c["slug"] for c in categories}
    catalog = [{"slug": c["slug"], "name": c["name"]} for c in categories]

    system = (
        "You classify personal finance transactions into ONE category from the provided catalog only. "
        "Respond with a single JSON object: {\"slug\": \"<catalog slug>\", \"confidence\": 0.0-1.0, \"reason\": \"short\"}. "
        "The slug MUST exactly match one of the catalog slugs. If uncertain, pick the closest slug anyway "
        "or use slug \"uncategorized\" only if present in the catalog."
    )
    user = json.dumps(
        {
            "description_normalized": description_normalized,
            "description_raw": description_raw,
            "catalog": catalog,
        }
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    ref = os.environ.get("OPENROUTER_HTTP_REFERER")
    if ref:
        headers["HTTP-Referer"] = ref

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content)
        slug = str(obj.get("slug", "")).strip()
        if slug not in slug_set:
            return None, f"model returned invalid slug: {slug!r}"
        return slug, None
    except Exception as exc:
        return None, str(exc)
```

- [ ] **Step 2: Commit**

```bash
git add backend/pfa/llm_category_suggest.py
git commit -m "feat(llm): OpenRouter category suggestion constrained to catalog"
```

---

### Task 3: HTTP route for suggestion

**Files:**

- Modify: `backend/pfa/categorization_api.py`

- [ ] **Step 1: Add response model and route** (near other `/transactions/{transaction_id}/...` handlers in `categorization_api.py`)

```python
from pfa.budget_service import list_categories
from pfa.llm_category_suggest import suggest_category_slug


class CategorySuggestionOut(BaseModel):
    category_id: UUID | None
    slug: str | None
    error: str | None


@router.post("/transactions/{transaction_id}/suggest-category", response_model=CategorySuggestionOut)
def suggest_category_for_transaction(transaction_id: UUID):
    with connect() as conn:
        tx = conn.execute(
            """
            SELECT description_raw, description_normalized
            FROM transactions WHERE id = %s
            """,
            (str(transaction_id),),
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        cats = list_categories(conn)

    slug, err = suggest_category_slug(
        description_raw=tx[0],
        description_normalized=tx[1],
        categories=cats,
    )
    if err or not slug:
        return CategorySuggestionOut(category_id=None, slug=None, error=err or "no suggestion")
    match = next((c for c in cats if c["slug"] == slug), None)
    if match is None:
        return CategorySuggestionOut(category_id=None, slug=None, error="slug not found after validation")
    return CategorySuggestionOut(category_id=UUID(str(match["id"])), slug=slug, error=None)
```

- [ ] **Step 2: Commit**

```bash
git add backend/pfa/categorization_api.py
git commit -m "feat(api): POST suggest-category via OpenRouter"
```

---

### Task 4: Seed default categories

**Files:**

- Modify: `backend/pfa/schema.sql`

- [ ] **Step 1: Append idempotent seeds after `CREATE TABLE categories` block**

```sql
INSERT INTO categories (slug, name) VALUES
  ('groceries', 'Groceries'),
  ('dining', 'Dining & restaurants'),
  ('transport', 'Transport'),
  ('utilities', 'Utilities'),
  ('income', 'Income'),
  ('transfers', 'Transfers'),
  ('healthcare', 'Healthcare'),
  ('entertainment', 'Entertainment'),
  ('shopping', 'Shopping'),
  ('fees', 'Fees & charges'),
  ('housing', 'Housing'),
  ('travel', 'Travel'),
  ('uncategorized', 'Uncategorized')
ON CONFLICT (slug) DO NOTHING;
```

- [ ] **Step 2: Commit**

```bash
git add backend/pfa/schema.sql
git commit -m "feat(schema): seed default categories for manual correction"
```

---

### Task 5: Unit test (mocked HTTP)

**Files:**

- Create: `backend/tests/test_llm_category_suggest.py`

- [ ] **Step 1: Test happy path and invalid slug rejection**

```python
import json
from unittest.mock import patch

import pytest

from pfa.llm_category_suggest import suggest_category_slug

def test_returns_none_when_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    slug, err = suggest_category_slug(
        description_normalized="starbucks",
        description_raw="STARBUCKS",
        categories=[{"id": "1", "slug": "dining", "name": "Dining"}],
    )
    assert slug is None
    assert "OPENROUTER_API_KEY" in (err or "")

def test_maps_json_slug(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    fake_response = {
        "choices": [
            {"message": {"content": json.dumps({"slug": "dining", "confidence": 0.9, "reason": "coffee"})}}
        ]
    }
    with patch("pfa.llm_category_suggest.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value.raise_for_status = lambda: None
        mock_client.return_value.__enter__.return_value.post.return_value.json.return_value = fake_response
        slug, err = suggest_category_slug(
            description_normalized="starbucks",
            description_raw="X",
            categories=[{"id": "a", "slug": "dining", "name": "Dining"}],
        )
    assert err is None
    assert slug == "dining"
```

- [ ] **Step 2: Run**

Run: `cd backend && uv run pytest tests/test_llm_category_suggest.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_llm_category_suggest.py
git commit -m "test(llm): category suggest helper"
```

---

### Task 6: Frontend API + Transactions UX hook

**Files:**

- Modify: `frontend/src/api/transactions.ts`
- Modify: `frontend/src/features/transactions/TransactionsPage.tsx`

- [ ] **Step 1: API wrapper**

```typescript
export type CategorySuggestion = {
  category_id: string | null
  slug: string | null
  error: string | null
}

export function suggestTransactionCategory(txId: string): Promise<CategorySuggestion> {
  return request<CategorySuggestion>(`/transactions/${txId}/suggest-category`, {
    method: 'POST',
  })
}
```

- [ ] **Step 2: In expanded row UI**, add button “Suggest with AI” that calls `suggestTransactionCategory(tx.id)` and, on success with `category_id`, sets the `<select>` value to that id (same as manual pick).

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && npm test -- --run`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/transactions.ts frontend/src/features/transactions/TransactionsPage.tsx
git commit -m "feat(ui): AI category suggestion button on transactions"
```

---

### Task 7: Statements page — collapsible add-account + clarity

**Files:**

- Modify: `frontend/src/features/statements/StatementsPage.tsx`
- Modify: `frontend/src/styles/features/statements-queue.css`

- [ ] **Step 1: Wrap the add-account `<form>` in `<details>`**

Use `open={...}` only if you implement controlled mode; simplest is **uncontrolled** `<details>` with `defaultOpen={accountOptions.length === 0}`.

```tsx
<details className="account-setup-details" defaultOpen={accountOptions.length === 0}>
  <summary className="account-setup-summary">
    {accountOptions.length === 0 ? 'Set up your first account' : 'Add account'}
  </summary>
  <form className="account-setup-card" ...>
```

Move the inner `<h3>` text into `<summary>` or remove duplicate heading inside the form.

- [ ] **Step 2: Ensure import queue section stays visible** below `<details>` (unchanged order).

- [ ] **Step 3: CSS**

```css
.account-setup-details {
  margin-top: 1rem;
}
.account-setup-summary {
  cursor: pointer;
  font-weight: 600;
  color: #e2e8f0;
  padding: 0.5rem 0;
  list-style: none;
}
.account-setup-summary::-webkit-details-marker {
  display: none;
}
.account-setup-details[open] .account-setup-summary {
  margin-bottom: 0.75rem;
}
```

- [ ] **Step 4: Update `StatementsPage.test.tsx`** expectations if headings changed (`findByRole('button', ...)` or `getByText(/add account/i)` for summary).

Run: `cd frontend && npm test -- --run src/features/statements/StatementsPage.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/statements/StatementsPage.tsx frontend/src/styles/features/statements-queue.css frontend/src/features/statements/StatementsPage.test.tsx
git commit -m "feat(ui): collapsible add-account on Statements"
```

---

### Task 8: Statements visual polish (incremental)

**Files:**

- Modify: `frontend/src/styles/features/statements-queue.css`
- Optionally modify: `frontend/src/features/statements/StatementsPage.tsx` (section headings only)

- [ ] **Step 1:** Add a short **page subtitle** under `<h2>Statements</h2>` (one sentence: queue imports + table).

- [ ] **Step 2:** Use consistent spacing tokens already in `app-shell.css` — increase gap between “Queue imports” and table via `.import-actions { margin-bottom: 1rem; }` if needed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/statements/StatementsPage.tsx frontend/src/styles/features/statements-queue.css
git commit -m "style(statements): subtitle and spacing"
```

---

### Task 9: Manual verification

- [ ] **Step 1:** Set `OPENROUTER_API_KEY` and restart API.

- [ ] **Step 2:** Confirm seeded categories appear in `GET /categories`.

- [ ] **Step 3:** On Transactions page, expand a row → “Suggest with AI” returns a category or shows API error banner.

- [ ] **Step 4:** On Statements, with ≥1 account, confirm add-account block starts **collapsed**; click summary → expands.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-02-openrouter-categories-and-statements-ux.md`.

**Two execution options:**

1. **Subagent-driven (recommended)** — Fresh subagent per task; **sub-skill:** superpowers:subagent-driven-development.

2. **Inline execution** — Batch tasks in one session; **sub-skill:** superpowers:executing-plans.

Which approach do you want?
