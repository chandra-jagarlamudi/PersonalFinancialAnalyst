---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: observability
status: Draft
---

# Kit: Observability

Structured logging, rate limiting, and LangSmith tracing across all request paths and pipeline stages.

## Requirements

### R1 — Structured JSON Logging
Every HTTP request produces a structured log entry.
- Log format: JSON, one object per line, to stdout
- Required fields: `timestamp` (ISO 8601), `request_id` (UUID), `user_id` (email or "anonymous"), `method`, `path`, `status_code`, `latency_ms`
- `request_id` propagated through entire request lifecycle (all downstream log calls include it)
- Log level configurable via `LOG_LEVEL` env var (default: INFO)
- Acceptance: `curl` to any endpoint; log line appears with all required fields; `latency_ms` is accurate

### R2 — Per-Token Rate Limiting
API access rate-limited per bearer token to prevent runaway agent loops.
- Limit configurable via env var (default: 60 requests/minute per token)
- Exceeding limit returns 429 with `Retry-After` header
- Limit enforced in-memory with sliding window algorithm
- Rate limit status included in response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Acceptance: 61st request within 60s window returns 429; first request of next window succeeds

### R3 — LangSmith MCP Tool Tracing
Every MCP tool invocation traced in LangSmith.
- Each tool call creates a LangSmith run with: tool name, input arguments, output, latency, token count
- Claude API calls within tools are child spans of the tool run
- `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` read from environment
- Tracing gracefully disabled if `LANGSMITH_API_KEY` not set (no crash, warning logged)
- Acceptance: Invoking `summarize_month` via MCP client creates visible trace in LangSmith UI

### R4 — LangSmith Ingestion Pipeline Tracing
Statement ingestion pipeline traced end-to-end in LangSmith.
- Single parent run per upload: spans for parse, normalize, dedup-check, DB write
- Span attributes: `source_bank`, `filename`, `transaction_count`, `duration_ms`
- Failed ingestion creates a run with error status and exception details
- Acceptance: Uploading a statement creates a multi-span trace in LangSmith

### R5 — Error Logging
Unhandled exceptions captured with full context.
- 500 errors log: exception type, message, stack trace, `request_id`
- Errors logged at ERROR level; warnings at WARN level
- No sensitive data (tokens, raw file content) in logs
- Acceptance: Triggering a 500 produces a log entry with stack trace; no token values visible in logs

## Cross-References
- auth: request_id and user_id available from auth middleware context
- mcp: tool call entry/exit points instrumented
- ingestion: parse/normalize/write stages instrumented
- analytics: Claude API calls wrapped in LangSmith child spans
- infra: `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LOG_LEVEL` env vars
