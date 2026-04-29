---
created: "2026-04-28"
last_edited: "2026-04-28"
domain: mcp
status: Draft
---

# Kit: MCP

MCP server exposing financial analysis tools to AI agents over HTTP SSE transport. Handles protocol, authentication, and tool registration.

## Requirements

### R1 — MCP SSE Transport
Server implements MCP protocol over HTTP SSE.
- `GET /sse` — SSE connection endpoint; streams MCP server events to client
- `POST /messages` — receives MCP messages from client
- Protocol version: MCP 2024-11-05 or latest stable
- Concurrent clients supported (at least 1 in single-user context, but not artificially limited)
- Acceptance: MCP client (Claude Desktop, mcp-cli) connects and lists available tools

### R2 — Tool Registration
All analytics tools registered and discoverable via MCP `tools/list`.
- Tools registered: `summarize_month`, `find_unusual_spend`, `list_recurring_subscriptions`
- Each tool has: name, description, JSON Schema for input parameters
- `tools/list` response matches registered tools exactly
- Acceptance: `tools/list` returns all 3 tools with correct schemas

### R3 — Tool Input Validation
Tool calls with invalid inputs return MCP error, not unhandled exception.
- Input validated against registered JSON Schema before handler invoked
- Schema validation error → MCP `isError: true` response with human-readable message
- Missing required parameters → specific error identifying missing fields
- Acceptance: Call `summarize_month` without required `month` param → error response, not 500

### R4 — Tool Call Authentication
MCP SSE connection requires valid bearer token.
- Bearer token passed in `Authorization` header on `GET /sse` connection request
- Invalid token → 401 before SSE stream established
- Token validated on each `POST /messages` request (not just on connect)
- Acceptance: Connecting without token returns 401; valid token connects successfully

### R5 — Tool Error Handling
Tool execution errors surfaced as MCP error responses, not dropped.
- Exceptions in tool handlers caught; returned as `isError: true` MCP response
- Error message human-readable for agent consumption
- Stack trace logged server-side but not exposed to client
- Acceptance: Tool that throws returns MCP error response; agent receives actionable message

### R6 — MCP Server Metadata
Server exposes correct metadata via MCP `initialize` handshake.
- Server name: "financial-hygiene-assistant"
- Server version from package metadata
- Capabilities: `tools` only (no resources, no prompts in v1)
- Acceptance: MCP `initialize` response contains correct name, version, capabilities

## Cross-References
- analytics: tool handlers delegate to analytics functions
- auth: bearer token validated by auth middleware on SSE connect and each message
- observability: each tool invocation wrapped in LangSmith trace; request logged
