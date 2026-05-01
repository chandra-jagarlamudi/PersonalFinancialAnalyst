"""Deterministic streaming chat turn (slice 10) — planner + tool invoke + SSE framing."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from pfa.trace_invoke import invoke_tool_traced


def format_sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def plan_tool_calls(message: str) -> list[tuple[str, dict]]:
    """Keyword router — maps user text to embedded tools (no external LLM)."""
    m = message.lower()
    if re.search(r"\b(summary|overview|ledger|totals?|aggregate)\b", m):
        return [("ledger_summary", {})]
    return []


def _summarize_ledger_result(payload: dict) -> str:
    return (
        f"Ledger summary: {payload['transaction_count']} transactions; "
        f"expenses (abs sum) {payload['expense_total_abs']}; "
        f"income {payload['income_total']}."
    )


async def stream_chat_turn(message: str) -> AsyncIterator[str]:
    calls = plan_tool_calls(message)
    if not calls:
        yield format_sse(
            {
                "type": "delta",
                "text": (
                    "I can answer using read-only ledger tools. "
                    "Ask for a **ledger summary** or **overview** to pull aggregates from Postgres."
                ),
            }
        )
        yield format_sse({"type": "done"})
        return

    last_result: dict | None = None
    for name, args in calls:
        yield format_sse({"type": "tool_call", "name": name, "arguments": args})
        last_result = await asyncio.to_thread(invoke_tool_traced, name, args)
        yield format_sse({"type": "tool_result", "name": name, "content": last_result})

    if last_result is not None:
        text = _summarize_ledger_result(last_result)
        yield format_sse({"type": "delta", "text": text})

    yield format_sse({"type": "done"})
