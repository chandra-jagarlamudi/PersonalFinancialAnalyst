---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: analytics
status: Draft
---

# Kit: Analytics

LLM-backed financial analysis: three MCP tools for AI agents plus a streaming HTTP chat endpoint for browser UI. All analysis is LLM-driven — no hardcoded rules or statistical thresholds.

## Requirements

### R1 — `summarize_month` Tool
Produces a natural-language financial summary for a given month.
- Input schema: `{ month: string (YYYY-MM), include_categories: boolean (default true) }`
- Fetches all transactions for the specified month from storage
- Passes transactions (date, description, amount, category, transaction_type) to Claude
- Claude produces: total income, total spend, spend by category, top 5 merchants, 2-3 notable observations
- Output: MCP text response containing the summary
- Returns error if no transactions found for specified month (not an empty summary)
- Acceptance: Call with a month that has data → response contains spend total and category breakdown

### R2 — `find_unusual_spend` Tool
Identifies transactions that appear anomalous relative to user's history.
- Input schema: `{ month: string (YYYY-MM), lookback_months: integer (default 3, max 12) }`
- Fetches transactions for target month AND lookback period from storage
- Passes full transaction set to Claude with instructions to identify outliers
- Claude identifies: unusually large one-time charges, spending in new categories, sudden increase in a recurring category
- Output: MCP text response listing unusual items with brief explanations
- Returns "no unusual spend detected" if Claude finds nothing notable (not an error)
- Acceptance: Inject a $2000 charge in a month; tool identifies it as unusual vs prior months

### R3 — `list_recurring_subscriptions` Tool
Detects and lists recurring charges from transaction history.
- Input schema: `{ lookback_months: integer (default 6, max 24) }`
- Fetches transactions for lookback period
- Passes transactions to Claude with instructions to identify recurring patterns
- Claude identifies: same merchant appearing monthly (or weekly/annually) with similar amounts
- Output: structured list — each item: merchant, frequency, estimated amount, last charged date
- Excludes clearly non-subscription debits (mortgage, rent, utilities) by merchant heuristic passed as context
- Acceptance: Three months with "Netflix $15.49" entries → tool lists Netflix as monthly subscription

### R4 — Transaction Context Formatting
Transactions formatted efficiently for Claude API consumption.
- Transactions serialized as compact CSV rows (not JSON) to minimize token count
- Header row included: `date,description,amount,type,category`
- Amounts formatted as plain decimals (no currency symbols in context)
- Context truncated to most recent N transactions if total exceeds token budget (default: 2000 transactions)
- Token count estimated before call; warning logged if approaching limit
- Acceptance: 1000 transactions formatted and passed to Claude without API error

### R5 — Claude API Integration
Tools make Claude API calls with appropriate configuration.
- Model: `claude-sonnet-4-6` (configurable via `ANTHROPIC_MODEL` env var)
- System prompt: establishes role as personal finance analyst with user's data
- Max tokens: 1024 per tool call (configurable)
- API key from `ANTHROPIC_API_KEY` env var
- API errors (rate limit, timeout) returned as MCP error responses with retry guidance
- Acceptance: Valid API key → tool returns Claude's response; invalid key → MCP error with clear message

### R6 — Prompt Caching
Repeated tool calls with same transaction data use prompt caching to reduce cost.
- Cache breakpoint placed after system prompt and transaction context
- Cache hit rate logged via LangSmith span attributes
- Acceptance: Second call with same month data has lower token count than first call (cache hit)

### R7 — `/chat` HTTP Streaming Endpoint
Natural-language question answering for the browser UI via streaming HTTP.
- `POST /chat` accepts `{ question: string, context_months: integer (default 3), history: [{role, content}] }`
- Fetches transactions for `context_months` lookback; formats as compact CSV context (same as R4)
- Sends question + history + transaction context to Claude
- Response streamed token-by-token as `text/event-stream` SSE
- Last 6 turns of `history` included for conversational continuity; older turns dropped
- Endpoint is browser-driven; protected by session cookie middleware + CSRF (see kit-auth.md R4, R6)
- Prompt caching applied to system prompt + transaction context block
- Acceptance: `POST /chat` with question about last month's spending → SSE stream returns markdown answer referencing real transactions

## Cross-References
- storage: reads via `get_transactions`, `get_monthly_totals`
- mcp: MCP tool handlers (R1–R3) registered in MCP server; output returned as MCP text response
- ui: `/chat` endpoint (R7) consumed by chat interface; tool proxy endpoints forward to R1–R3 functions
- observability: each Claude API call is LangSmith child span; token counts logged
- infra: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` env vars
