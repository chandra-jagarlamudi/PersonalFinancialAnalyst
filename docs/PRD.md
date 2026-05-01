# PRD: Personal Finance MCP server + agent-driven UI (self-hosted MVP)

Canonical copy of [GitHub Issue #1](https://github.com/chandra-jagarlamudi/PersonalFinancialAnalyst/issues/1). Prefer discussing changes in that issue; update this document when the PRD is revised.

---

## Problem Statement

I want a single-user, self-hosted personal finance system that can ingest bank and credit card statements (CSV and selected PDF formats), normalize them into a PostgreSQL ledger, and expose structured tools to an AI agent so I can get accurate budgeting, analysis, and conversational insights without manually wrangling spreadsheets.

Today, statement data is fragmented across institutions and formats. Manual tracking is time-consuming, error-prone, and hard to keep up to date. Generic “chat with your finances” tools either can’t ingest reliably, don’t provide trustworthy normalization/deduplication, or lack actionable workflows (budgets, recurring, anomalies) that respect privacy.

## Solution

Build a self-hosted web app with a backend-run AI agent and an embedded MCP-shaped tool layer.

Users can upload statements (CSV + targeted credit card PDF first). Uploads are processed asynchronously into a canonical transaction ledger in Postgres with strong deduplication. The UI provides a budgeting-first experience (monthly envelope budgets) plus charts and chat. The agent uses structured tools to answer questions, generate analyses, and propose changes, but must request confirmation before any write.

The system defaults to privacy-preserving behavior: send aggregates to the LLM provider by default and only send minimal line-item details on explicit user drilldown. LangSmith is used for tracing agent/tool calls.

## User Stories

1. As a single user, I want to run the app locally (localhost by default), so that my financial data stays on my machine.
2. As a user, I want password login with a secure session, so that my data isn’t accessible to anyone else who can reach my machine.
3. As a user, I want to upload a CSV statement, so that my transactions can be ingested reliably.
4. As a user, I want to upload a supported credit card PDF statement, so that I can ingest my primary card even when CSV export is inconvenient.
5. As a user, I want uploads to complete in the background, so that the UI remains responsive.
6. As a user, I want to see ingestion progress by step (extract → normalize → dedupe → categorize → persist), so that I can trust what’s happening.
7. As a user, I want ingestion results to show counts (rows parsed/inserted/deduped), so that I can quickly spot problems.
8. As a user, I want ingestion failures to show a clear error, so that I can fix the input or report a bug.
9. As a user, I want raw statement files stored locally with metadata, so that I can re-run derived computations without re-uploading.
10. As a user, I want the system to detect re-uploaded identical statements, so that I don’t create duplicates.
11. As a user, I want transaction-level deduplication across overlapping statements, so that my ledger stays correct.
12. As a user, I want each transaction to retain both transaction date and posted date when available, so that time-series views are accurate.
13. As a user, I want a consistent signed-amount convention (income vs expense), so that analysis is predictable.
14. As a user, I want my institutions and accounts represented explicitly, so that I can separate spending by account.
15. As a user, I want account aliases, so that minor naming differences don’t split my ledger.
16. As a user, I want a standard set of categories, so that I can start budgeting immediately.
17. As a user, I want to customize categories (add/rename/merge) while keeping stable identifiers, so that budgets and history remain intact.
18. As a user, I want my transactions categorized automatically using deterministic rules first, so that most items are categorized quickly and predictably.
19. As a user, I want the system to use the LLM only for unknown/low-confidence categorization, so that I don’t waste tokens and reduce leakage of sensitive data.
20. As a user, I want to manually correct a transaction’s category, so that I can fix mistakes.
21. As a user, I want the system to propose a rule after I correct a category (apply to future, optionally retroactively), so that future imports improve.
22. As a user, I want to create monthly envelope budgets per category, so that I can plan spending.
23. As a user, I want a simple budget editor table, so that I can manage budgets quickly.
24. As a user, I want a “suggest budgets from history” action, so that setup is faster.
25. As a user, I want budget status to default to month-to-date with projections, so that I can see if I’m on track.
26. As a user, I want to view cashflow (income vs expenses) over time, so that I understand my baseline.
27. As a user, I want to view category spending over time, so that I can compare against budgets.
28. As a user, I want to see recurring monthly charges (same merchant, similar amount, ≥3 occurrences), so that I can manage subscriptions.
29. As a user, I want to see anomalies (spend spikes, new merchants, unusually large transactions) detected deterministically, so that I can trust the alerts.
30. As a user, I want the agent to explain anomalies and suggest actions, so that I understand what changed.
31. As a user, I want chat to stream responses, so that the experience feels responsive.
32. As a user, I want to ask questions like “Why was March so expensive?” and get answers grounded in ledger data, so that insights are trustworthy.
33. As a user, I want chat answers to use aggregates by default, so that I minimize sharing raw line-item details with the LLM provider.
34. As a user, I want to drill down (“Explain this charge”) and explicitly allow minimal line-item context to be sent, so that I can resolve specific questions.
35. As a user, I want the agent to be able to run read-only queries and use high-level tools, so that analysis is flexible but safe.
36. As a user, I want the agent to ask for confirmation before any data-changing action, so that I stay in control.
37. As a user, I want an ingestion review gate to trigger only when parser confidence is low, so that I don’t have to review every import.
38. As a user, I want to soft-delete data by default, so that I can undo mistakes.
39. As a user, I want a permanent purge option, so that I can fully delete sensitive data including raw files.
40. As a user, I want to re-run derived computations (recategorize, re-score anomalies, re-normalize merchant names) without changing canonical transactions, so that improvements don’t rewrite history.
41. As a user, I want the system to support multiple LLM providers behind a stable interface, so that I can switch providers later.
42. As a user, I want tool calls and key agent steps traced in LangSmith, so that I can debug and audit agent behavior.
43. As a user, I want the UI to have both a dedicated Upload page and chat-driven workflows, so that I can choose the most convenient interaction.
44. As a user, I want charts to update after ingestion completes, so that I can immediately see results.
45. As a user, I want ingestion to be idempotent across retries, so that transient failures don’t create duplicates.

## Implementation Decisions

- **Deployment model**
  - Single-user self-hosted.
  - Backend binds to localhost by default; future option to expose externally.

- **Service topology**
  - One backend service containing:
    - An embedded MCP-shaped tool layer (tool schemas + deterministic implementations).
    - The agent runtime (backend-run).
  - Frontend is a separate web client that calls the backend.

- **Auth and safety**
  - Password login with secure session cookie.
  - Confirm-before-write policy for agent: any tool that mutates state requires explicit user confirmation.

- **Ingestion workflow**
  - Asynchronous job model with a Postgres-backed durable queue.
  - Step-level job status tracking with timestamps, counts, and surfaced errors.
  - Raw uploaded files stored on disk with DB metadata and immutable content hash.
  - Statement-level idempotency via file hash.
  - Transaction-level dedupe via deterministic fingerprint and unique constraints.
  - Import review gate only when parser confidence is low or validation signals trigger.

- **Parsing scope and approach**
  - MVP supports CSV ingestion and one targeted credit card PDF statement format.
  - PDF extraction ladder: table extraction → text-line parsing → OCR fallback.

- **Canonical data model (high level)**
  - Entities: institution, account, account alias, statement, transaction, category, categorization rule, budget, recurring series, anomaly signal.
  - Transactions include both transaction date and posted date (when present), signed amount convention, currency, raw and normalized description fields, source institution/account identifiers, and a `dedupe_fingerprint`.
  - Categories are standard-by-default but user-customizable with stable internal identifiers.

- **Derived computations and reprocessing**
  - Support reprocessing derived fields (e.g., merchant normalization, categorization, anomaly scoring) without rewriting canonical transaction rows.

- **Categorization strategy**
  - Rules-first deterministic categorization.
  - LLM used only for unknown/low-confidence cases; results cached.
  - Manual corrections can apply to a single transaction and propose a general rule for future (and optional retroactive application).

- **Analytics MVP scope**
  - Envelope-style monthly budgets with MTD + projection.
  - Recurring detection: monthly cadence, same merchant + similar amount, ≥3 occurrences.
  - Anomaly detection: deterministic signals and simple robust stats; LLM produces explanations after detection.

- **Agent tool surface**
  - Provide high-level read tools (cashflow, budget status, recurring, anomalies, category breakdown).
  - Provide a restricted read-only SQL query tool as an escape hatch for development and complex analysis.
  - Privacy boundary: aggregates by default; drilldown sends minimal necessary raw data.

- **Observability**
  - Integrate LangSmith for agent/tool call traces.

- **UI/UX**
  - Dedicated Upload page plus chat commands.
  - Streaming chat responses.
  - Job progress via polling (streaming for jobs deferred).

## Testing Decisions

- **What makes a good test**
  - Tests should validate external behavior and invariants (idempotency, dedupe correctness, parsing outcomes, tool contracts), not internal implementation details.

- **Modules to test**
  - Normalization + dedupe fingerprint generation (pure functions; deterministic outputs).
  - CSV ingestion parser (mapping → canonical transaction records).
  - Targeted PDF parser (given fixture PDFs, produces expected rows and confidence signals).
  - Categorization engine (rules-first behavior; LLM fallback mocked).
  - Recurring detection and anomaly detection (stable outputs on known datasets).
  - Postgres-backed job queue semantics (enqueue, run, retry, status transitions).
  - Agent tool contracts (input validation, output schemas, read-only enforcement).

- **Prior art**
  - Follow existing repository testing patterns (pytest-style) if present; otherwise establish a standard layout with deterministic fixtures and golden-file expectations for parsers.

## Out of Scope

- Multi-tenant SaaS, billing, and enterprise auth.
- Full “generic PDF parsing for any institution” beyond the targeted first credit card format.
- Real-time streaming of job step updates (SSE/WebSocket) in MVP.
- Full observability stack beyond step-level statuses + LangSmith.
- Automated bank connection (Plaid/open banking) in MVP.
- Full “financial advice” or regulated recommendations; the agent provides analytics and summaries, not professional advice.

## Further Notes

- Privacy defaults are critical: most questions can be answered from aggregates; line-item sharing should require explicit user intent.
- The readonly SQL tool is valuable for iteration but should be gated (auth + readonly enforcement) and potentially removed or locked down when exposing the service beyond localhost.
- Parser confidence scoring is important to make the “review only when needed” gate trustworthy.
