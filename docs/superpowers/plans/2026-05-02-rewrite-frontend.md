# Frontend Structural Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the PersonalFinancialAnalyst Vite + React frontend into feature-oriented folders, extract the authenticated shell and login UI from `App.tsx`, split the monolithic `api.ts` and `App.css` into maintainable modules—while preserving identical runtime behavior, routes, and test coverage.

**Architecture:** Route-level screens live under `src/features/<feature>/` with optional co-located CSS. The application shell (nav, session-aware layout) and login flow live under `src/app/`. HTTP helpers and domain-specific API functions live under `src/api/` as named modules re-exported from `src/api/index.ts`, so feature imports stay `from '@/api'`. Global tokens and layout primitives remain in `src/styles/`; feature-specific rules migrate beside components incrementally. Vitest and `react-router-dom` stay unchanged.

**Tech Stack:** React 19, react-router-dom 7, Vite 8, TypeScript 6, Vitest 4 + Testing Library, ESLint 10. Global CSS only (no Tailwind/shadcn added in this plan—YAGNI).

---

## File structure (target)

| Path | Responsibility |
|------|----------------|
| `frontend/src/main.tsx` | Entry; imports global CSS then `App`. |
| `frontend/src/App.tsx` | Thin bootstrap: session bootstrap + `BrowserRouter` + auth gate; delegates to `AppShell` or `LoginForm`. |
| `frontend/src/app/auth/LoginForm.tsx` | Login form UI and submit handler (presentational + callbacks). |
| `frontend/src/app/layout/AppShell.tsx` | Header, nav `Link`s, `<Routes>` wiring for protected views. |
| `frontend/src/app/layout/Overview.tsx` | Home/overview panel (welcome + metric strip). |
| `frontend/src/app/layout/SmokePage.tsx` | Protected API smoke-check copy + status. |
| `frontend/src/app/layout/types.ts` | Shared `ProtectedState` type used by shell + overview + smoke. |
| `frontend/src/features/statements/StatementsPage.tsx` | Statements list + ingest queue. |
| `frontend/src/features/transactions/TransactionsPage.tsx` | Transactions list. |
| `frontend/src/features/transactions/TransactionDetailPage.tsx` | Single transaction detail. |
| `frontend/src/features/budget/BudgetPage.tsx` | Budget editor + status. |
| `frontend/src/features/recurring/RecurringPage.tsx` | Recurring charges. |
| `frontend/src/features/anomalies/AnomaliesPage.tsx` | Anomalies list. |
| `frontend/src/features/chat/ChatPage.tsx` | Streaming chat. |
| `frontend/src/api/http.ts` | `request`, `postMultipart`, shared fetch helpers. |
| `frontend/src/api/session.ts` | `SessionState`, `getSession`, `login`, `logout`. |
| `frontend/src/api/budgets.ts` | Budget + category list/create types and calls. |
| `frontend/src/api/recurring.ts` | Recurring types + `listRecurring`. |
| `frontend/src/api/statements.ts` | Statements + institutions + accounts. |
| `frontend/src/api/transactions.ts` | Transactions, detail, categorization, rules. |
| `frontend/src/api/anomalies.ts` | `AnomalySignal`, `listAnomalies`. |
| `frontend/src/api/ingest.ts` | `IngestJob*` types, enqueue CSV/PDF, `getIngestJob`, `pollIngestJob`. |
| `frontend/src/api/chat.ts` | `streamChat`. |
| `frontend/src/api/index.ts` | Re-exports every **public** symbol previously exported from `api.ts` (do **not** export internal `request`/`postMultipart` unless the old file did). |
| `frontend/src/styles/app-shell.css` | Shell, auth card, nav, shared primitives (extracted from `App.css`). |
| `frontend/src/styles/features/statements.css` | Statements + import queue. |
| `frontend/src/styles/features/recurring.css` | `.recurring-*` rules. |
| `frontend/src/styles/features/budget.css` | `.budget-*` rules. |

---

### Task 1: Add `@/` path alias (Vite + TypeScript)

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/tsconfig.app.json`

- [ ] **Step 1: Patch `vite.config.ts`**

Add Node URL helper and `resolve.alias`:

```typescript
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
const srcDir = fileURLToPath(new URL('./src', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': srcDir },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
```

- [ ] **Step 2: Patch `tsconfig.app.json`**

Inside `compilerOptions`, add:

```json
"baseUrl": ".",
"paths": {
  "@/*": ["src/*"]
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run build`

Expected: `tsc -b && vite build` completes with exit code 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.ts frontend/tsconfig.app.json
git commit -m "chore(frontend): add @ path alias for src"
```

---

### Task 2: Extract HTTP helpers to `src/api/http.ts`

**Files:**
- Create: `frontend/src/api/http.ts`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Create `http.ts`** — Cut `RequestOptions`, `request`, and `postMultipart` from `frontend/src/api.ts` into `frontend/src/api/http.ts` and export both functions. (Paste body verbatim from current lines 35–68 and 324–345.)

- [ ] **Step 2: In `api.ts`**, remove duplicated implementations and add:

```typescript
import { postMultipart, request } from './api/http'
```

Use path `./api/http` because `api.ts` lives in `src/`; `http.ts` lives in `src/api/http.ts`.

- [ ] **Step 3: Run**

`cd frontend && npm test && npm run build`

- [ ] **Step 4: Commit** `refactor(frontend): extract api http helpers`

---

### Task 3: Add `ProtectedState` type module

**Files:**
- Create: `frontend/src/app/layout/types.ts`

```typescript
export type ProtectedState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; categoryCount: number }
  | { status: 'error'; message: string }
```

- [ ] Commit `refactor(frontend): add ProtectedState type module`

---

### Task 4: Extract `LoginForm`

**Files:**
- Create: `frontend/src/app/auth/LoginForm.tsx`
- Modify: `frontend/src/App.tsx`

Move lines 20–69 (`LoginForm` function) into `LoginForm.tsx` as named export `LoginForm` (full JSX unchanged). In `App.tsx`:

```typescript
import { LoginForm } from './app/auth/LoginForm'
```

- [ ] `npm test` && commit `refactor(frontend): extract LoginForm`

---

### Task 5–11: Move feature pages (order: move pages **before** extracting `AppShell` **or** keep relative imports until moves done)

Move each page into `frontend/src/features/<name>/` and switch imports to `@/api`.

| Current | New |
|---------|-----|
| `src/StatementsPage.tsx` | `src/features/statements/StatementsPage.tsx` |
| `src/StatementsPage.test.tsx` | `src/features/statements/StatementsPage.test.tsx` |
| `src/TransactionsPage.tsx` | `src/features/transactions/TransactionsPage.tsx` |
| `src/TransactionsPage.test.tsx` | `src/features/transactions/TransactionsPage.test.tsx` |
| `src/TransactionDetailPage.tsx` | `src/features/transactions/TransactionDetailPage.tsx` |
| `src/BudgetPage.tsx` | `src/features/budget/BudgetPage.tsx` |
| `src/BudgetPage.test.tsx` | `src/features/budget/BudgetPage.test.tsx` |
| `src/RecurringPage.tsx` | `src/features/recurring/RecurringPage.tsx` |
| `src/RecurringPage.test.tsx` | `src/features/recurring/RecurringPage.test.tsx` |
| `src/AnomaliesPage.tsx` | `src/features/anomalies/AnomaliesPage.tsx` |
| `src/ChatPage.tsx` | `src/features/chat/ChatPage.tsx` |

- [ ] After each move: `import … from '@/api'` in moved `.tsx` files; tests import `./ComponentName` locally.

- [ ] **Verify:** `cd frontend && npm test && npm run build`

- [ ] **Commits:** one commit per feature folder or one grouped `refactor(frontend): move feature pages under src/features`

---

### Task 12: Extract `Overview`, `SmokePage`, `AppShell`

**Files:**
- Create: `frontend/src/app/layout/Overview.tsx` (from `App.tsx` lines 72–117)
- Create: `frontend/src/app/layout/SmokePage.tsx` (119–140)
- Create: `frontend/src/app/layout/AppShell.tsx` — rename `Shell` → `AppShell`; import feature pages from `@/features/...`

Example `AppShell` imports:

```typescript
import AnomaliesPage from '@/features/anomalies/AnomaliesPage'
import BudgetPage from '@/features/budget/BudgetPage'
import ChatPage from '@/features/chat/ChatPage'
import { RecurringPage } from '@/features/recurring/RecurringPage'
import StatementsPage from '@/features/statements/StatementsPage'
import TransactionDetailPage from '@/features/transactions/TransactionDetailPage'
import TransactionsPage from '@/features/transactions/TransactionsPage'
```

- [ ] Slim `App.tsx` to session/bootstrap only; render `<AppShell … />` when authenticated.

- [ ] `npm test && npm run build` && commit `refactor(frontend): extract AppShell and overview routes`

---

### Task 13: Replace `src/api.ts` with `src/api/*.ts` + `index.ts`

- [ ] Create domain modules (`session.ts`, `budgets.ts`, `statements.ts`, `transactions.ts`, `recurring.ts`, `anomalies.ts`, `ingest.ts`, `chat.ts`) by moving code from `api.ts`, each importing `request` / `postMultipart` from `./http`.

- [ ] Create `frontend/src/api/index.ts`:

```typescript
export * from './anomalies'
export * from './budgets'
export * from './chat'
export * from './ingest'
export * from './recurring'
export * from './session'
export * from './statements'
export * from './transactions'
```

Do **not** `export * from './http'` unless consumers needed `request` publicly (they did not).

- [ ] Delete `frontend/src/api.ts`. Ensure `@/api` resolves to `src/api/index.ts`.

- [ ] `npm test && npm run build` && commit `refactor(frontend): split api into domain modules`

---

### Task 14: Split `App.css`

- [ ] Create `frontend/src/styles/` partials; use a barrel `frontend/src/styles/index.css` with `@import` of `app-shell.css` and `features/*.css`.

- [ ] Import barrel from `frontend/src/main.tsx` after `./index.css`:

```typescript
import './index.css'
import '@/styles/index.css'
```

- [ ] Remove `import './App.css'` from `App.tsx` when styles migrated; delete `App.css` when empty.

- [ ] `npm run build` && commit `refactor(frontend): split global CSS`

---

### Task 15: README

- [ ] Document `src/app`, `src/features`, `src/api` in `README.md` frontend section.

- [ ] Commit `docs: describe frontend folder layout`

---

## Self-review

- **Spec coverage:** Folder layout, API split, CSS split, shell extraction each have tasks.
- **Exports:** `index.ts` must mirror **public** exports of old `api.ts` only—omit internal `request`.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-05-02-rewrite-frontend.md`.

**1. Subagent-driven (recommended)** — superpowers:subagent-driven-development  
**2. Inline** — superpowers:executing-plans  

Prefer an isolated **git worktree** (superpowers:using-git-worktrees) before multi-commit refactors.

**Which approach do you want?**
