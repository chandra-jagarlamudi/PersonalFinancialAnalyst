---
created: "2026-04-28"
last_edited: "2026-04-28"
---
# Implementation Tracking: UI

Build site: context/plans/build-site.md

| Task | Status | Notes |
|------|--------|-------|
| T-071 | DONE | Vite react-ts scaffold in frontend/, docker-compose frontend service, devcontainer port 5173, vite proxy /api → backend |
| T-072 | DONE | api.ts: apiFetch/apiFetchMultipart/streamChat, CSRF cookie read, 401→/login redirect, network error toast, all endpoints typed |
| T-073 | DONE | AuthContext (useAuth hook), LoginPage ("Sign in with Google" → /api/auth/login), App.tsx AuthGuard + createBrowserRouter |
| T-074 | DONE | DevBanner: sticky yellow banner when authEnabled===false, non-dismissable |
| T-075 | DONE | UploadPage.tsx: drag-drop/click-browse, bank dropdown, spinner, success card, 409/400 handling |
| T-076 | DONE | SummaryPage.tsx: 3 tabs (Month Summary/Unusual/Subscriptions), month+lookback selectors, markdown render |
| T-077 | DONE | TransactionsPage.tsx: 7-col table, date/bank/category/type filters, full-text search, CSV export, pagination |
| T-078 | DONE | SummaryPage.tsx (same file as T-076): recharts pie/bar/horizontal-bar charts, shared month selector |
| T-079 | DONE | ChatPage.tsx: streaming SSE, markdown bubbles, Clear history, last-6-turns context, Enter to send |
| T-080 | DONE | Layout.tsx: sidebar nav with NavLink active highlight, user email + Sign out |
