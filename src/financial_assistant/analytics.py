"""T-061/T-062/T-063: Analytics functions — summarize_month, find_unusual_spend,
list_recurring_subscriptions.

Each function:
- Fetches transactions from storage via injected session
- Formats via context_formatter (T-058)
- Calls Claude via claude_client (T-059/T-060)
- Wraps in LangSmith trace span
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from financial_assistant.claude_client import ClaudeError, call_claude
from financial_assistant.context_formatter import format_transactions_csv
from financial_assistant.queries import get_transactions
from financial_assistant.tracing import trace_span

log = structlog.get_logger()

_EXCLUDE_RECURRING_MERCHANTS = (
    "mortgage", "rent", "electric", "gas company", "water utility",
    "internet", "cable", "insurance",
)


async def summarize_month(
    db: AsyncSession,
    month: str,
    include_categories: bool = True,
) -> str:
    """T-061: Return natural-language financial summary for the given month (YYYY-MM)."""
    year, mon = _parse_month(month)
    start = date(year, mon, 1)
    end = _month_end(year, mon)

    with trace_span("summarize_month", inputs={"month": month, "include_categories": include_categories}):
        txns = await get_transactions(db, start_date=start, end_date=end)
        if not txns:
            raise ValueError(f"No transactions found for {month}")

        ctx, estimated_tokens = format_transactions_csv(txns)
        log.info("analytics.summarize_month", month=month, rows=len(txns), estimated_tokens=estimated_tokens)

        category_instruction = (
            "Include a breakdown by spending category." if include_categories else ""
        )
        prompt = (
            f"Summarize my finances for {month}. "
            f"Include: total income, total spend, top 5 merchants, and 2-3 notable observations. "
            f"{category_instruction}".strip()
        )

        try:
            text, usage = await call_claude(
                prompt,
                transaction_context=ctx,
                extra_metadata={"tool": "summarize_month", "month": month},
            )
        except ClaudeError as exc:
            raise RuntimeError(str(exc)) from exc

    return text


async def find_unusual_spend(
    db: AsyncSession,
    month: str,
    lookback_months: int = 3,
) -> str:
    """T-062: Identify anomalous transactions vs lookback period."""
    lookback_months = min(lookback_months, 12)
    year, mon = _parse_month(month)
    target_start = date(year, mon, 1)
    target_end = _month_end(year, mon)

    # Lookback window starts N months before the target month
    lb_year, lb_mon = _months_ago(year, mon, lookback_months)
    lb_start = date(lb_year, lb_mon, 1)

    with trace_span("find_unusual_spend", inputs={"month": month, "lookback_months": lookback_months}):
        # Fetch target month + lookback in one call
        txns = await get_transactions(db, start_date=lb_start, end_date=target_end)
        if not txns:
            return "No transactions found for the specified period."

        ctx, estimated_tokens = format_transactions_csv(txns)
        log.info(
            "analytics.find_unusual_spend",
            month=month,
            lookback_months=lookback_months,
            rows=len(txns),
            estimated_tokens=estimated_tokens,
        )

        prompt = (
            f"Analyze my transactions for {month} compared to the prior {lookback_months} months "
            f"(data starts {lb_start}). "
            "Identify: unusually large one-time charges, spending in new categories, "
            "or sudden increases in a recurring category. "
            "If nothing is unusual, respond with 'No unusual spend detected this month.'"
        )

        try:
            text, usage = await call_claude(
                prompt,
                transaction_context=ctx,
                extra_metadata={"tool": "find_unusual_spend", "month": month},
            )
        except ClaudeError as exc:
            raise RuntimeError(str(exc)) from exc

    return text


async def list_recurring_subscriptions(
    db: AsyncSession,
    lookback_months: int = 6,
) -> str:
    """T-063: Detect recurring charges and return structured list."""
    lookback_months = min(lookback_months, 24)
    today = date.today()
    year, mon = today.year, today.month
    lb_year, lb_mon = _months_ago(year, mon, lookback_months)
    lb_start = date(lb_year, lb_mon, 1)

    with trace_span("list_recurring_subscriptions", inputs={"lookback_months": lookback_months}):
        txns = await get_transactions(db, start_date=lb_start, end_date=today)
        if not txns:
            return "No transactions found for the specified period."

        ctx, estimated_tokens = format_transactions_csv(txns)
        log.info(
            "analytics.list_recurring_subscriptions",
            lookback_months=lookback_months,
            rows=len(txns),
            estimated_tokens=estimated_tokens,
        )

        exclude_hint = ", ".join(_EXCLUDE_RECURRING_MERCHANTS)
        prompt = (
            f"Identify recurring subscriptions and charges in my transactions over the last "
            f"{lookback_months} months (since {lb_start}). "
            "For each, output: merchant name, frequency (monthly/weekly/annual), "
            "estimated amount, and last charged date. "
            f"Exclude obvious non-subscriptions like: {exclude_hint}. "
            "Format as a structured list."
        )

        try:
            text, usage = await call_claude(
                prompt,
                transaction_context=ctx,
                extra_metadata={"tool": "list_recurring_subscriptions"},
            )
        except ClaudeError as exc:
            raise RuntimeError(str(exc)) from exc

    return text


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_month(month: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' → (year, month_int). Raises ValueError on bad format."""
    try:
        parts = month.split("-")
        if len(parts) != 2:
            raise ValueError
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise ValueError(f"month must be YYYY-MM format, got {month!r}")


def _month_end(year: int, month: int) -> date:
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def _months_ago(year: int, month: int, n: int) -> tuple[int, int]:
    """Return (year, month) N months before (year, month)."""
    total = year * 12 + (month - 1) - n
    return total // 12, total % 12 + 1
