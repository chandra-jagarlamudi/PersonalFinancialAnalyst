"""Streaming chat HTTP routes (slice 10)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pfa.agent_tools import list_tool_specs
from pfa.chat_agent import stream_chat_turn

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatStreamBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


@router.get("/tools")
def http_list_tools():
    """MCP-shaped tool manifests for discovery (embedded agent)."""
    return list_tool_specs()


@router.post("/stream")
async def http_chat_stream(body: ChatStreamBody):
    return StreamingResponse(
        stream_chat_turn(body.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
