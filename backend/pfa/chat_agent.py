"""Deterministic streaming chat turn — keyword planner + read-only tool invoke + SSE framing."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from pfa.trace_invoke import invoke_tool_traced as invoke_tool


def format_sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _extract_sql_query(message: str) -> str | None:
    fence = re.search(r"```(?:sql)?\s*(.*?)```", message, re.DOTALL | re.IGNORECASE)
    if fence:
        q = fence.group(1).strip()
        if q:
            return q
    stripped = message.strip()
    if re.match(r"(?is)^(WITH|SELECT)\b", stripped):
        return stripped
    return None


def _maybe_year_month(text: str) -> str | None:
    m = re.search(r"\b(20\d{2})-(\d{2})\b", text)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def plan_tool_calls(message: str) -> list[tuple[str, dict]]:
    """Keyword router — maps user text to embedded tools (no external LLM)."""
    sql_q = _extract_sql_query(message)
    if sql_q:
        return [("sql_select", {"query": sql_q})]

    m = message.lower()
    calls: list[tuple[str, dict]] = []

    if re.search(r"\b(summary|overview|ledger|totals?|aggregate)\b", m):
        calls.append(("ledger_summary", {}))

    if re.search(r"\b(budget|envelope|mtd)\b", m):
        ym = _maybe_year_month(message)
        calls.append(("budget_status", {} if ym is None else {"year_month": ym}))

    if re.search(r"\b(cashflow|cash flow|income vs expense|monthly trend)\b", m):
        calls.append(("cashflow_monthly", {"months": 6}))

    if re.search(r"\b(recurring|subscription)\b", m):
        calls.append(("recurring_highlights", {"limit": 8}))

    if re.search(r"\b(anomal|spike|new merchant)\b", m):
        calls.append(("anomalies_summary", {"lookback_days": 120}))

    if re.search(r"\b(category breakdown|spending by category|by category)\b", m):
        ym = _maybe_year_month(message)
        if ym is None:
            from datetime import date

            d = date.today()
            ym = f"{d.year}-{d.month:02d}"
        calls.append(("category_breakdown", {"year_month": ym}))

    return calls


def summarize_tool_result(name: str, payload: dict) -> str:
    if name == "ledger_summary":
        return (
            f"Ledger summary: {payload['transaction_count']} transactions; "
            f"expenses (abs sum) {payload['expense_total_abs']}; "
            f"income {payload['income_total']}."
        )
    if name == "budget_status":
        lines = payload.get("lines") or []
        if not lines:
            return (
                f"Budget status for {payload.get('year_month')}: no envelope lines for that month "
                f"(create budgets first)."
            )
        parts = [
            f"{x['name']}: budget {x['budget_amount']}, spent MTD {x['spent_mtd']}, "
            f"remaining MTD {x['remaining_mtd']}"
            for x in lines[:12]
        ]
        more = f" (+{len(lines) - 12} more categories)" if len(lines) > 12 else ""
        return f"Budget status ({payload.get('year_month')}, as_of {payload.get('as_of')}):\n" + "\n".join(
            parts
        ) + more
    if name == "cashflow_monthly":
        series = payload.get("series") or []
        if not series:
            return "Cashflow: no transactions in the requested window."
        lines = [
            f"{s['month']}: expenses {s['expenses_abs']}, income {s['income']}" for s in series[:12]
        ]
        return "Monthly cashflow (recent months):\n" + "\n".join(lines)
    if name == "recurring_highlights":
        items = payload.get("items") or []
        if not items:
            return "Recurring highlights: no merchants met the ≥3 occurrence cadence rule yet."
        lines = [
            f"{x['merchant']}: ~{x['typical_amount']} across {x['occurrences']} charges "
            f"({x['first_seen']} → {x['last_seen']})"
            for x in items
        ]
        return "Recurring-style charges (deterministic heuristic):\n" + "\n".join(lines)
    if name == "anomalies_summary":
        counts = payload.get("counts_by_kind") or {}
        total = payload.get("total_signals", 0)
        head = f"Anomaly signals (total {total}): " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts.items())
        )
        prev = payload.get("preview") or []
        if not prev:
            return head + "."
        lines = [f"- {p['kind']} / {p['merchant']} @ {p['transaction_date']}: {p['detail']}" for p in prev]
        return head + "\n" + "\n".join(lines)
    if name == "category_breakdown":
        lines = payload.get("lines") or []
        if not lines:
            return f"Category breakdown {payload.get('year_month')}: no categorized outflows in range."
        parts = [f"{x['name']}: {x['spent_abs']}" for x in lines[:15]]
        return f"Category spending {payload.get('year_month')}:\n" + "\n".join(parts)
    if name == "sql_select":
        return (
            f"SQL read-only result: {payload['row_count']} row(s), "
            f"columns {', '.join(payload.get('columns') or [])}."
        )
    return json.dumps(payload, default=str)[:2000]


async def stream_chat_turn(message: str) -> AsyncIterator[str]:
    calls = plan_tool_calls(message)
    if not calls:
        yield format_sse(
            {
                "type": "delta",
                "text": (
                    "I answer with read-only ledger tools (aggregates first). Try asking for a "
                    "**ledger summary**, **budget** status, **cashflow**, **recurring** charges, "
                    "**anomalies**, or **category breakdown**. For advanced analysis you can paste a "
                    "single fenced ```sql SELECT … LIMIT n ``` block (n ≤ 500). "
                    "This MVP does not execute silent writes; anything that changes data would "
                    "need an explicit confirmation flow that is not wired yet."
                ),
            }
        )
        yield format_sse({"type": "done"})
        return

    summaries: list[str] = []
    for name, args in calls:
        yield format_sse({"type": "tool_call", "name": name, "arguments": args})
        try:
            result = await asyncio.to_thread(invoke_tool, name, args)
        except Exception as exc:
            yield format_sse(
                {
                    "type": "tool_result",
                    "name": name,
                    "error": {"type": exc.__class__.__name__, "message": str(exc)},
                }
            )
            summaries.append(f"{name}: error — {exc}")
            continue
        yield format_sse({"type": "tool_result", "name": name, "content": result})
        summaries.append(summarize_tool_result(name, result))

    yield format_sse({"type": "delta", "text": "\n\n".join(summaries)})
    yield format_sse({"type": "done"})
