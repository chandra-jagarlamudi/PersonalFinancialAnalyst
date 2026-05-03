# Account types (catalog) and multi-account creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users add more than one account after the first, and require each account to reference a **controlled account type** (Checking, Savings, Credit Card, Mortgage, Trading, etc.) loaded from the database (seeded defaults), exposed via API for the UI.

**Architecture:** Introduce an `account_types` lookup table seeded at schema apply time (same pattern as other idempotent DDL in `schema.sql`). Extend `accounts` with a foreign key to `account_types`. Add `GET /account-types` for the frontend dropdown and extend `POST/GET /accounts` to carry `account_type_id` (required on create). Replace the Statements-page UX that only shows the onboarding form when `accounts.length === 0` with an always-available **Add account** flow (same fields + type select), keeping onboarding prominent when the list is empty.

**Tech Stack:** PostgreSQL 16, FastAPI, Pydantic v2, psycopg 3; frontend Vite + React + TypeScript, Vitest + Testing Library.

---

## File structure (creates / modifies)

| Path | Responsibility |
|------|----------------|
| `backend/pfa/schema.sql` | New `account_types` table; seed rows; `accounts.account_type_id` column + FK + backfill for existing DBs. |
| `backend/pfa/setup_api.py` | `AccountTypeOut`, `GET /account-types`; extend `AccountIn` / `AccountOut`; validate `account_type_id` on create; join type on list. |
| `backend/tests/test_setup_http.py` | **Create** — HTTP tests for account types list + account create with type (if file missing, create alongside edits to `test_job_http.py` helpers). |
| `backend/tests/test_job_http.py` | Update `_setup_account` to resolve an `account_type_id` from `GET /account-types` (or fixture). |
| Other tests posting `/accounts` | Grep for `"/accounts"` and update payloads (see Task 4). |
| `frontend/src/api/statements.ts` | Types + `listAccountTypes()`, extend account types with `account_type_id` + optional nested type label for display. |
| `frontend/src/features/statements/StatementsPage.tsx` | Account-type `<select>` (required); **Add account** form visible whenever user needs another account (not only at zero accounts). |
| `frontend/src/styles/features/statements-queue.css` | Layout for secondary “Add another account” block if needed. |
| `frontend/src/features/statements/StatementsPage.test.tsx` | Mocks extended for `GET /account-types`; tests for second-account flow. |

---

### Self-review (plan author)

**Spec coverage**

| Requirement | Task |
|-------------|------|
| Create a second (and further) accounts | Task 5 |
| Account types from a fixed catalog (not free-form semantics for “type”) | Tasks 1–3 |
| Catalog from DB (recommended) vs config file | Task 1 chooses DB+seed; Appendix A documents config-only alternative |

**Placeholder scan:** No TBD/TODO in tasks below.

**Type consistency:** `account_type_id` is UUID end-to-end; `AccountOut` includes joined labels for display.

---

### Task 1: Schema — `account_types` + `accounts.account_type_id`

**Files:**

- Modify: `backend/pfa/schema.sql`

- [ ] **Step 1: Append DDL and seed (idempotent)**

Add after the `accounts` table definition (before `ingest_jobs`), following existing style (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`):

```sql
CREATE TABLE IF NOT EXISTS account_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

INSERT INTO account_types (code, label, sort_order) VALUES
  ('checking', 'Checking', 10),
  ('savings', 'Savings', 20),
  ('credit_card', 'Credit Card', 30),
  ('mortgage', 'Mortgage', 40),
  ('trading', 'Trading', 50),
  ('other', 'Other', 990)
ON CONFLICT (code) DO NOTHING;

ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS account_type_id UUID REFERENCES account_types(id);

UPDATE accounts
SET account_type_id = (SELECT id FROM account_types WHERE code = 'other' LIMIT 1)
WHERE account_type_id IS NULL;

ALTER TABLE accounts
  ALTER COLUMN account_type_id SET NOT NULL;
```

**Note:** Ensure seed `INSERT` runs before `UPDATE`/`SET NOT NULL`. If `ON CONFLICT DO NOTHING` means no rows on first run, first insert must succeed—use `INSERT ... SELECT WHERE NOT EXISTS` if your deployment forbids blind INSERT (optional hardening).

- [ ] **Step 2: Commit**

```bash
git add backend/pfa/schema.sql
git commit -m "feat(schema): account_types lookup and accounts.account_type_id"
```

---

### Task 2: API models and routes — list types, create/list accounts with type

**Files:**

- Modify: `backend/pfa/setup_api.py`

- [ ] **Step 1: Add models and `GET /account-types`**

```python
class AccountTypeOut(BaseModel):
    id: UUID
    code: str
    label: str
    sort_order: int


@router.get("/account-types", response_model=list[AccountTypeOut])
def list_account_types():
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, code, label, sort_order
                FROM account_types
                ORDER BY sort_order, label
                """
            )
            return [AccountTypeOut(**row) for row in cur.fetchall()]
```

- [ ] **Step 2: Extend `AccountIn` / `AccountOut`**

```python
class AccountIn(BaseModel):
    institution_id: UUID
    account_type_id: UUID
    name: str
    currency: str = "USD"


class AccountOut(BaseModel):
    id: UUID
    institution_id: UUID
    account_type_id: UUID
    account_type_label: str
    name: str
    currency: str
```

- [ ] **Step 3: Update `create_account`**

After validating institution exists, validate type exists:

```python
        type_ok = conn.execute(
            "SELECT 1 FROM account_types WHERE id = %s",
            (str(body.account_type_id),),
        ).fetchone()
        if type_ok is None:
            raise HTTPException(status_code=404, detail="account type not found")
```

Use `INSERT INTO accounts (institution_id, account_type_id, name, currency) ... RETURNING id, institution_id, account_type_id, name, currency`, then load `account_type_label` from `account_types` by `account_type_id`.

- [ ] **Step 4: Update `list_accounts`**

Join `account_types` and return `account_type_label`.

- [ ] **Step 5: Run backend tests (expect failures until Task 4 updates helpers)**

Run: `cd backend && pytest tests/test_job_http.py -q --tb=no`

Expected: failures on `/accounts` POST until Task 4.

- [ ] **Step 6: Commit**

```bash
git add backend/pfa/setup_api.py
git commit -m "feat(api): account types catalog and required account_type_id"
```

---

### Task 3: Backend HTTP tests for account types + account create

**Files:**

- Create: `backend/tests/test_setup_http.py`

- [ ] **Step 1: Write tests**

```python
"""Setup API: institutions, accounts, account types."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_list_account_types_ordered(client):
    r = client.get("/account-types")
    assert r.status_code == 200
    types = r.json()
    assert len(types) >= 6
    codes = [t["code"] for t in types]
    assert "checking" in codes and "other" in codes


def test_create_account_requires_valid_account_type_id(client):
    inst = client.post("/institutions", json={"name": "T Bank"}).json()
    r = client.post(
        "/accounts",
        json={
            "institution_id": inst["id"],
            "account_type_id": "00000000-0000-4000-8000-000000000001",
            "name": "Nope",
        },
    )
    assert r.status_code == 404


def test_create_account_with_type_returns_label(client):
    inst = client.post("/institutions", json={"name": "U Bank"}).json()
    types = client.get("/account-types").json()
    checking = next(t for t in types if t["code"] == "checking")
    r = client.post(
        "/accounts",
        json={
            "institution_id": inst["id"],
            "account_type_id": checking["id"],
            "name": "Primary",
            "currency": "USD",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["account_type_id"] == checking["id"]
    assert body["account_type_label"] == "Checking"
    assert body["name"] == "Primary"
```

- [ ] **Step 2: Run**

Run: `cd backend && pytest tests/test_setup_http.py -v`

Expected: PASS after Task 2.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_setup_http.py
git commit -m "test(api): account types and typed account creation"
```

---

### Task 4: Update all integration tests that POST `/accounts`

**Files:**

- Modify: `backend/tests/test_job_http.py` and any test file under `backend/tests/` that posts to `/accounts`.

- [ ] **Step 1: Update `_setup_account` in `test_job_http.py`**

Resolve `account_type_id` from `GET /account-types` (use `checking` code) and include it in the POST body.

- [ ] **Step 2: Grep and fix**

Run: `rg '"/accounts"' backend/tests -n` and update every payload.

- [ ] **Step 3: Full backend suite**

Run: `cd backend && pytest -q`

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests
git commit -m "test: pass account_type_id when creating accounts in integration tests"
```

---

### Task 5: Frontend API types and Statements page UX

**Files:**

- Modify: `frontend/src/api/statements.ts`
- Modify: `frontend/src/features/statements/StatementsPage.tsx`
- Modify: `frontend/src/styles/features/statements-queue.css` (only if layout needs it)
- Modify: `frontend/src/features/statements/StatementsPage.test.tsx`

- [ ] **Step 1: Extend `frontend/src/api/statements.ts`**

Add types and list function:

```typescript
export type AccountType = {
  id: string
  code: string
  label: string
  sort_order: number
}

export type Account = {
  id: string
  institution_id: string
  account_type_id: string
  account_type_label: string
  name: string
  currency: string
}

export function listAccountTypes(): Promise<AccountType[]> {
  return request<AccountType[]>('/account-types')
}
```

Change `createAccount` to require `account_type_id: string` in its argument object (alongside `institution_id`, `name`, `currency`).

- [ ] **Step 2: StatementsPage — state and `load()`**

Add:

```typescript
const [accountTypes, setAccountTypes] = useState<AccountType[]>([])
const [setupAccountTypeId, setSetupAccountTypeId] = useState('')
```

In `load()`, extend the inner `Promise.all` to include `listAccountTypes()` (three-way or four-way parallel with statements already loaded outer). After setting `accountTypes` from the result, if `setupAccountTypeId` is empty and the list is non-empty, call `setSetupAccountTypeId(accountTypes[0].id)`.

- [ ] **Step 3: Add account form always visible**

Replace the condition `accountOptions.length === 0 ? form : null` with unconditional render of the same `<form className="account-setup-card">`.

Set `<h3>` to:

```tsx
{accountOptions.length === 0 ? 'Add your first account' : 'Add another account'}
```

Inside `account-setup-fields`, before institution name, add:

```tsx
<label>
  Account type
  <select
    value={setupAccountTypeId}
    onChange={e => setSetupAccountTypeId(e.target.value)}
    disabled={setupBusy || accountTypes.length === 0}
    aria-label="Account type"
    required
  >
    {accountTypes.length === 0 ? (
      <option value="">Loading types…</option>
    ) : (
      accountTypes.map(t => (
        <option key={t.id} value={t.id}>
          {t.label}
        </option>
      ))
    )}
  </select>
</label>
```

Rename `handleCreateFirstAccount` to `handleCreateAccount` and pass `account_type_id: setupAccountTypeId` into `createAccount`. Validate `setupAccountTypeId` before submit.

- [ ] **Step 4: Import target dropdown labels**

Where options map accounts, use:

```tsx
const label = inst ? `${inst.name} — ${a.name} (${a.account_type_label})` : `${a.name} (${a.account_type_label})`
```

- [ ] **Step 5: Vitest — mock `GET /account-types`**

Insert one mock response `{ body: [ { id: 'type-checking', code: 'checking', label: 'Checking', sort_order: 10 }, ... ] }` in the fetch sequence **before** or **with** the same batch as accounts/institutions, matching the order of `fetch` calls in `load()`.

Add test: mock one existing account (non-empty `listAccounts`), render page, expect heading `/add another account/i` and that `createAccount` receives `account_type_id` when form is submitted (spy or mock last POST).

- [ ] **Step 6: Run**

Run: `cd frontend && npm test -- --run`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/statements.ts frontend/src/features/statements/StatementsPage.tsx frontend/src/styles/features/statements-queue.css frontend/src/features/statements/StatementsPage.test.tsx
git commit -m "feat(ui): account type catalog and add-another-account on Statements"
```

---

### Task 6: Manual verification

- [ ] **Step 1:** Start API + DB per README.

- [ ] **Step 2:** `curl -s http://127.0.0.1:$API_PORT/account-types` — expect seeded types.

- [ ] **Step 3:** On `/statements`, create first account with a non-default type; then use **Add another account** for a second account.

- [ ] **Step 4:** Confirm import dropdown lists both accounts with labels.

---

## Appendix A — Alternative: types from a config file (no `account_types` table)

Define `backend/pfa/account_types.yaml` with `code` / `label` / `sort_order`, load at startup, expose the same `GET /account-types` JSON shape, store `account_type` **TEXT** on `accounts` with `CHECK` constraints. **Tradeoff:** changing types requires deploy; DB seed supports evolution without code changes for labels/order.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-02-account-types-and-multi-account-creation.md`.

**Two execution options:**

1. **Subagent-driven (recommended)** — Fresh subagent per task; **sub-skill:** superpowers:subagent-driven-development.

2. **Inline execution** — Batched tasks with checkpoints; **sub-skill:** superpowers:executing-plans.

Which approach do you want?
