---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: ui
status: Draft
---

# Kit: UI

React + Vite single-page application providing browser-based access to all system capabilities: statement upload, tool output viewing, transaction browsing, spend visualization, and natural-language chat. Handles Google OAuth login flow.

## Requirements

### R1 — Auth Flow
UI drives the Google OAuth 2.0 login and session lifecycle via HttpOnly cookie.
- Unauthenticated users see login page with "Sign in with Google" button
- Button triggers redirect to `GET /auth/login` (server initiates OAuth flow)
- After OAuth callback, server sets session cookie and redirects browser to app root — no token visible to JavaScript
- All API requests use `credentials: 'include'` so browser automatically sends session cookie
- On 401 response: UI redirects to login page (no localStorage to clear)
- "Sign out" button calls `POST /auth/logout` (session cookie sent automatically); server deletes session and clears cookie; UI redirects to login page
- Acceptance: Full browser login flow completes; subsequent API calls succeed with cookie; logout invalidates session; no credential stored in localStorage or accessible to JavaScript

### R2 — Auth Bypass Toggle
Development mode allows disabling authentication for faster local iteration.
- Server reads `DISABLE_AUTH` env var; when `true`, all endpoints accept requests without token
- `GET /auth/status` returns `{ auth_enabled: boolean }` — UI reads this on startup
- When auth disabled, UI skips login page and shows a persistent yellow banner: "Auth disabled — dev mode"
- Banner not dismissable
- Acceptance: Set `DISABLE_AUTH=true`, reload UI → login page skipped, banner visible on all pages

### R3 — Statement Upload Page
Drag-and-drop file upload interface for ingesting bank statements.
- Accepts PDF and CSV files; drag-and-drop zone + click-to-browse
- Bank selector dropdown (Chase, Amex, Capital One, Robinhood) with "auto-detect" default
- Upload progress indicator (indeterminate spinner — no byte-level progress needed)
- On success: shows `{ bank_detected, transaction_count, period_start, period_end }` inline
- On 409 (duplicate): shows "Already ingested" message with original ingestion date
- On 400: shows specific validation error
- Multiple files uploadable sequentially (not batch — one at a time)
- Acceptance: Drag CSV onto zone, select bank, submit → success card with transaction count appears

### R4 — Tool Output Viewer
UI for invoking and displaying results of the three MCP analytics tools.
- Three tabs or cards: "Month Summary", "Unusual Spend", "Subscriptions"
- Month Summary: month picker (YYYY-MM) → calls `POST /tools/summarize_month` → renders markdown response
- Unusual Spend: month picker + lookback selector (1–12 months) → calls `POST /tools/find_unusual_spend` → renders markdown
- Subscriptions: lookback selector (1–24 months) → calls `POST /tools/list_recurring_subscriptions` → renders structured list (not markdown)
- Loading state shown while awaiting response
- Error state shown if tool returns error
- Acceptance: Select a month with data → summary renders with category breakdown visible

### R5 — Transaction Browser
Searchable, filterable table of all stored transactions.
- Columns: Date, Description, Merchant, Amount, Type (debit/credit), Category, Bank
- Filters: date range picker, bank selector (multi-select), category selector (multi-select), transaction type toggle
- Full-text search on Description and Merchant fields (client-side filter on loaded data)
- Pagination: 100 rows per page
- Amounts color-coded: debits red, credits green
- CSV export button: downloads currently filtered view as CSV
- Acceptance: Filter by Chase + last 30 days → only Chase transactions in range shown; export produces valid CSV

### R6 — Spend Visualizations
Charts showing spending patterns over time.
- Category breakdown: pie or donut chart for selected month (by spend amount)
- Monthly trend: bar chart showing total spend per month for last 6 months
- Top merchants: horizontal bar chart, top 10 merchants by total spend in selected period
- All charts use same month/date range selector as Tool Output Viewer (shared state)
- Charts render within 500ms of data load (client-side render from pre-fetched transaction data)
- Acceptance: Select month → three charts render with correct totals matching transaction data

### R7 — Natural Language Chat
Conversational interface for ad-hoc financial questions.
- Chat input box at bottom; message history scrolls above
- User types question (e.g., "How much did I spend on food last month?")
- UI calls `POST /chat` with `{ question, context_months }` (default last 3 months of context)
- Response streams token-by-token via SSE; rendered as markdown in chat bubble
- Chat history persists in browser session (not server-side)
- "Clear history" button resets conversation
- Context window: last 6 chat turns sent with each request for conversational continuity
- Acceptance: Ask "What's my biggest expense category?" → streamed markdown answer appears referencing real transaction data

### R8 — Navigation and Layout
Consistent app shell across all pages.
- Sidebar or top nav: Upload, Summary, Transactions, Chat
- Active route highlighted in nav
- User email shown in header, fetched from `GET /auth/me` on app load (server reads active session and returns `{ email }`)
- "Dev mode" banner (R2) always visible at top when active
- Responsive: usable on laptop viewport (min 1024px); no mobile requirement
- Acceptance: Navigating between all sections works without page reload; active section highlighted

### R9 — API Client Layer
All server communication goes through a typed client module.
- Single module wraps all `fetch` calls to server HTTP endpoints
- All requests use `credentials: 'include'` so session cookie is sent automatically by browser
- All state-changing requests (POST) include `X-CSRF-Token` header (value read from CSRF cookie set by server)
- On 401: redirects to login page
- On network error: surfaces user-facing toast notification
- No raw `fetch` calls outside this module
- Acceptance: Valid session → API calls succeed; 401 response → redirect to login; state-changing requests include CSRF header

## HTTP Endpoints Required from Server (non-MCP)
UI needs these server HTTP endpoints (not MCP protocol):
- `GET /auth/status` → `{ auth_enabled: boolean }`
- `GET /auth/me` → `{ email: string }` — returns authenticated user's email from active session
- `POST /tools/summarize_month` → proxies to analytics, returns text
- `POST /tools/find_unusual_spend` → proxies to analytics, returns text
- `POST /tools/list_recurring_subscriptions` → proxies to analytics, returns structured JSON
- `GET /transactions` → paginated transaction list with filter params
- `POST /chat` → streaming SSE response (see kit-analytics R7)

## Cross-References
- auth: login flow, session cookie, bypass toggle, CSRF protection
- analytics: tool outputs + chat endpoint
- ingestion: upload endpoint
- storage: transaction list endpoint reads from DB
- observability: UI-initiated requests logged and traced same as agent requests
- infra: `frontend/` added to docker compose; Vite port 5173 forwarded in devcontainer
