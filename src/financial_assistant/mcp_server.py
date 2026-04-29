"""MCP SSE transport endpoints.

T-055: GET /sse streaming + POST /messages endpoints (MCP 2024-11-05)
T-056: initialize handshake — server name + version from package metadata, tools capability
T-057: MCP API key validated on every POST /messages (via MCPApiKeyMiddleware in main.py)
"""

from __future__ import annotations

from importlib.metadata import version as pkg_version

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import Response
from mcp.server import Server
from mcp.server.sse import SseServerTransport

log = structlog.get_logger()

router = APIRouter()

_server_version: str
try:
    _server_version = pkg_version("financial-assistant")
except Exception:
    _server_version = "0.1.0"

# Singleton MCP server — tools registered in T-064 once analytics functions exist.
mcp_server = Server(
    name="financial-hygiene-assistant",
    version=_server_version,
)

# Transport handles session routing between /sse and /messages.
_sse_transport = SseServerTransport("/messages")


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
