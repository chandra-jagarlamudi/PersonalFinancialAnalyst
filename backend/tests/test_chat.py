"""Agent chat streaming + MCP-shaped tools (slice 10)."""

from __future__ import annotations

import asyncio
import datetime
import json
import uuid

import pytest

from pfa.chat_agent import format_sse, plan_tool_calls, stream_chat_turn


def _parse_sse(body: str) -> list[dict]:
    events = []
    for line in body.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_plan_tool_calls_triggers_on_summary_keyword():
    assert plan_tool_calls("Give me a ledger summary") == [("ledger_summary", {})]


def test_plan_tool_calls_empty_when_smalltalk():
    assert plan_tool_calls("Hello there") == []


def test_format_sse_emits_json_line():
    assert format_sse({"type": "done"}) == 'data: {"type": "done"}\n\n'


def test_stream_chat_fallback_without_tools():
    async def collect():
        parts = []
        async for chunk in stream_chat_turn("Hello"):
            parts.append(chunk)
        return "".join(parts)

    raw = asyncio.run(collect())
    events = _parse_sse(raw)
    assert any(e.get("type") == "delta" for e in events)
    assert events[-1] == {"type": "done"}


@pytest.mark.integration
def test_get_chat_tools_manifest(client):
    r = client.get("/chat/tools")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = {x["name"] for x in body}
    assert "ledger_summary" in names


@pytest.mark.integration
def test_chat_stream_ledger_summary_tool(client, sample_account_id, clean_db):
    aid = str(sample_account_id)
    with clean_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transactions (
              account_id, transaction_date, amount, currency,
              description_raw, description_normalized, dedupe_fingerprint
            ) VALUES (%s, %s, %s, 'USD', 'coffee', 'coffee', %s)
            """,
            (aid, datetime.date(2025, 4, 1), "-12.50", f"fp-{uuid.uuid4()}"),
        )
    clean_db.commit()

    with client.stream("POST", "/chat/stream", json={"message": "Please summarize my ledger"}) as r:
        assert r.status_code == 200
        raw = "".join(c.decode("utf-8") for c in r.iter_bytes())

    events = _parse_sse(raw)
    assert {"type": "tool_call", "name": "ledger_summary", "arguments": {}} in events
    results = [e for e in events if e.get("type") == "tool_result"]
    assert len(results) == 1
    assert results[0]["content"]["transaction_count"] == 1
    assert results[0]["content"]["expense_total_abs"] == "12.5000"
    deltas = [e for e in events if e.get("type") == "delta"]
    assert any("12.5000" in d["text"] for d in deltas)
    assert events[-1] == {"type": "done"}
