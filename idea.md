Build a Financial Hygiene Assistant MCP server: an AI‑facing API that ingests PDF/CSV statements, normalizes transactions into Postgres, and exposes tools for summarization, anomaly detection, and budgeting.

1. System context

- The MCP server is a Python service exposing tools to an AI agent.
- The agent’s job: help you understand and improve your finances by:
  - Ingesting PDF/CSV bank and card statements.
  - Normalizing them into a consistent transaction schema in Postgres (Docker).  
  - Answering questions via tools like “summarize this month,” “find unusual spend,” “list recurring subscriptions.”

Auth and infra:

- User login: Google OAuth 2.0 to identify you as the owner of the data.
- API security: bearer tokens (from OAuth) required on HTTP endpoints.
- Observability:
  - Structured JSON logging for every request (request_id, user_id, latency, status).
  - Rate limiting (per user / per API key) to show systems thinking.
  - LangSmith integration for tracing and call costs