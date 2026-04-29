---
created: "2026-04-28"
last_edited: "2026-04-28"
---

# Cavekit Overview

## Project
Financial Hygiene Assistant — MCP server exposing personal finance tools to AI agents. Ingests PDF/CSV bank/card statements, normalizes transactions into Postgres, answers financial questions via LLM-backed tools.

## Domain Index
| Domain | File | Summary | Status |
|--------|------|---------|--------|
| ingestion | kit-ingestion.md | Upload endpoint + bank-specific parsers (Chase, Amex, CapOne, Robinhood) + normalization | Draft |
| storage | kit-storage.md | Postgres schema, Alembic migrations, transaction model | Draft |
| mcp | kit-mcp.md | MCP SSE server, tool registration, protocol layer | Draft |
| analytics | kit-analytics.md | LLM-backed tools + /chat streaming endpoint for UI | Draft |
| auth | kit-auth.md | Google OAuth 2.0, bearer tokens, single-user config, DISABLE_AUTH bypass toggle | Draft |
| observability | kit-observability.md | Structured JSON logging, rate limiting, LangSmith tracing | Draft |
| infra | kit-infra.md | Docker Compose, devcontainer.json, env config | Draft |
| ui | kit-ui.md | React + Vite SPA: upload, tool viewer, transaction browser, charts, chat | Draft |

## Cross-Reference Map
| Domain A | Interacts With | Interaction Type |
|----------|---------------|-----------------|
| ingestion | storage | writes normalized transactions |
| ingestion | observability | traces ingestion pipeline steps |
| mcp | analytics | MCP tool handlers call analytics functions |
| mcp | auth | middleware validates every tool call |
| mcp | observability | traces each tool invocation |
| analytics | storage | reads transactions for analysis |
| analytics | observability | LangSmith traces Claude API calls |
| analytics | ui | /chat SSE endpoint + tool proxy endpoints consumed by browser |
| auth | observability | logs auth events |
| auth | ui | OAuth login flow driven by UI; DISABLE_AUTH toggle read by UI |
| ui | ingestion | upload form calls POST /upload |
| ui | storage | transaction browser calls GET /transactions |
| infra | storage | provisions Postgres container |
| infra | ui | frontend/ container + Vite port in devcontainer |

## Dependency Graph
```
infra → storage → ingestion → analytics → ui
                            ↗             ↑
auth → observability → mcp ──────────────┘
```
Build order: infra → storage → auth → observability → ingestion → mcp → analytics → ui
