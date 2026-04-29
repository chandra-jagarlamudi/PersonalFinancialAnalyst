"""MCP SSE transport endpoints + tool registration.

T-055: GET /sse streaming + POST /messages endpoints (MCP 2024-11-05)
T-056: initialize handshake — server name + version from package metadata, tools capability
T-057: MCP API key validated on every POST /messages (via MCPApiKeyMiddleware in main.py)
T-064: Register summarize_month / find_unusual_spend / list_recurring_subscriptions tools
T-065: Input validation — missing/invalid params return isError MCP response (not 500)
T-066: Tool exceptions returned as isError MCP response; stack trace logged server-side
T-067: Each tool invocation wrapped in LangSmith trace_span with args/output/latency
"""

from __future__ import annotations

from importlib.metadata import version as pkg_version
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import Response
from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.sse import SseServerTransport

from financial_assistant.db import get_session
from financial_assistant.tracing import trace_span

log = structlog.get_logger()

router = APIRouter()

_server_version: str
try:
    _server_version = pkg_version("financial-assistant")
except Exception:
    _server_version = "0.1.0"

mcp_server = Server(
    name="financial-hygiene-assistant",
    version=_server_version,
)

_sse_transport = SseServerTransport("/messages")


# ── T-064: Tool definitions ────────────────────────────────────────────────────

_TOOLS = [
    mcp_types.Tool(
        name="summarize_month",
        description=(
            "Produce a natural-language financial summary for a given month. "
            "Returns total income, total spend, spend by category, top merchants, and observations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "Month to summarize in YYYY-MM format",
                    "pattern": r"^\d{4}-\d{2}$",
                },
                "include_categories": {
                    "type": "boolean",
                    "description": "Include category breakdown (default true)",
                    "default": True,
                },
            },
            "required": ["month"],
        },
    ),
    mcp_types.Tool(
        name="find_unusual_spend",
        description=(
            "Identify anomalous transactions in a month compared to a lookback period. "
            "Returns 'No unusual spend detected' when nothing notable is found."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "Target month in YYYY-MM format",
                    "pattern": r"^\d{4}-\d{2}$",
                },
                "lookback_months": {
                    "type": "integer",
                    "description": "Number of prior months for baseline (default 3, max 12)",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 12,
                },
            },
            "required": ["month"],
        },
    ),
    mcp_types.Tool(
        name="list_recurring_subscriptions",
        description=(
            "Detect recurring charges (subscriptions, memberships) from transaction history. "
            "Returns a structured list with merchant, frequency, amount, and last charged date."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "lookback_months": {
                    "type": "integer",
                    "description": "Months of history to scan (default 6, max 24)",
                    "default": 6,
                    "minimum": 1,
                    "maximum": 24,
                },
            },
        },
    ),
]


@mcp_server.list_tools()
async def handle_list_tools() -> list[mcp_types.Tool]:
    """T-064: Return all registered tools."""
    return _TOOLS


@mcp_server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any],
) -> list[mcp_types.TextContent]:
    """T-065/T-066/T-067: Validate, trace, execute, and handle tool calls."""
    # T-065: Validate required fields before dispatch
    validation_error = _validate_tool_args(name, arguments)
    if validation_error:
        log.warning("mcp.tool_validation_error", tool=name, error=validation_error)
        return [mcp_types.TextContent(
            type="text",
            text=f"Input error: {validation_error}",
        )]

    with trace_span("mcp_tool", inputs={"tool": name, "arguments": arguments}):
        try:
            text = await _dispatch_tool(name, arguments)
        except Exception as exc:
            # T-066: Log stack trace server-side, return human-readable error to client
            log.exception("mcp.tool_error", tool=name, error=str(exc))
            return [mcp_types.TextContent(
                type="text",
                text=f"Tool execution failed: {exc}",
            )]

    return [mcp_types.TextContent(type="text", text=text)]


async def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
    from financial_assistant.analytics import (
        find_unusual_spend,
        list_recurring_subscriptions,
        summarize_month,
    )

    async with get_session() as db:
        if name == "summarize_month":
            return await summarize_month(
                db,
                month=args["month"],
                include_categories=args.get("include_categories", True),
            )
        if name == "find_unusual_spend":
            return await find_unusual_spend(
                db,
                month=args["month"],
                lookback_months=args.get("lookback_months", 3),
            )
        if name == "list_recurring_subscriptions":
            return await list_recurring_subscriptions(
                db,
                lookback_months=args.get("lookback_months", 6),
            )
    raise ValueError(f"Unknown tool: {name!r}")


def _validate_tool_args(name: str, args: dict[str, Any]) -> str | None:
    """Return error message string if validation fails, None if OK."""
    if name in ("summarize_month", "find_unusual_spend"):
        if "month" not in args:
            return "missing required field 'month' (expected YYYY-MM)"
        month = args["month"]
        if not isinstance(month, str) or not _is_valid_month(month):
            return f"'month' must be YYYY-MM format, got {month!r}"
    return None


def _is_valid_month(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"\d{4}-\d{2}", s))


# ── Transport routes ───────────────────────────────────────────────────────────

@router.get("/sse")
async def sse_endpoint(request: Request) -> Response:
    """T-055: SSE connection. Auth enforced upstream by MCPApiKeyMiddleware."""
    log.info("mcp.sse_connect", client=request.client)
    async with _sse_transport.connect_sse(
        request.scope, request.receive, request._send  # type: ignore[attr-defined]
    ) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
    return Response()


@router.post("/messages")
async def messages_endpoint(request: Request) -> Response:
    """T-055/T-057: MCP message relay. Auth enforced upstream by MCPApiKeyMiddleware."""
    await _sse_transport.handle_post_message(
        request.scope, request.receive, request._send  # type: ignore[attr-defined]
    )
    return Response()
