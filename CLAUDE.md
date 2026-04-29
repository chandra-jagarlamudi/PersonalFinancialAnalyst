# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Financial Hygiene Assistant — an MCP server exposing personal finance tools to AI agents. Ingests PDF/CSV bank/card statements, normalizes transactions into Postgres, and answers financial questions.

## Planned Stack

- **MCP server:** Python
- **Database:** PostgreSQL via Docker
- **Auth:** Google OAuth 2.0; bearer tokens required on all HTTP endpoints
- **Observability:** Structured JSON logging (fields: `request_id`, `user_id`, `latency`, `status`), per-user/per-API-key rate limiting, LangSmith tracing + cost analysis

## Architecture Layers

```
AI Agent
   │  MCP tool calls
   ▼
MCP Server (Python)
   │  reads/writes
   ▼
PostgreSQL (Docker)   ←── Statement Ingestion (PDF/CSV parsers → normalized transaction schema)
```

## Core MCP Tools (from spec)

| Tool | Purpose |
|------|---------|
| `summarize_month` | Financial summary for a time period |
| `find_unusual_spend` | Anomaly detection on transaction history |
| `list_recurring_subscriptions` | Detect and list recurring charges |

## Key Design Decisions

- Postgres runs in Docker for local dev portability — not a managed cloud DB
- All HTTP endpoints require bearer tokens derived from Google OAuth flow
- Rate limiting enforced at API level, not application logic
- LangSmith used for MCP tool call tracing and cost visibility
