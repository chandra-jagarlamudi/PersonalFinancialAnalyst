"""Embedded MCP-shaped read tools for the backend-run agent."""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from pfa.anomalies import detect_anomalies, load_expense_window_and_first_seen
from pfa.budget_service import BudgetServiceError, budget_status, parse_year_month
from pfa.db import connect
from pfa.recurring import TxRow, detect_recurring

MONEY_PLACES = Decimal("0.0001")

_SQL_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)


def list_tool_specs() -> list[dict[str, Any]]:
    """JSON-schema-shaped manifests for agent discovery."""
    return [
        {
            "name": "ledger_summary",
            "description": (
                "Aggregate transaction counts and signed-amount totals from the ledger. "
                "Uses sums over all rows unless account_id scopes to one account."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Optional account UUID to filter transactions.",
                    },
                },
            },
        },
        {
            "name": "budget_status",
            "description": (
                "Envelope budget lines for a calendar month with MTD spend and linear projection "
                "(aggregates only)."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "year_month": {
                        "type": "string",
                        "description": "YYYY-MM for budget month (defaults to current month).",
                    },
                },
            },
        },
        {
            "name": "cashflow_monthly",
            "description": (
                "Monthly aggregate expenses (absolute outflows) and income totals over recent months."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "months": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 36,
                        "description": "How many trailing calendar months to include (default 6).",
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Optional account UUID filter.",
                    },
                },
            },
        },
        {
            "name": "recurring_highlights",
            "description": (
                "Deterministic recurring charge candidates (same merchant cadence); returns "
                "top merchants by occurrences."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "account_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
            },
        },
        {
            "name": "anomalies_summary",
            "description": (
                "Deterministic anomaly signals (large spends vs merchant median, monthly spikes, "
                "new merchants) as counts plus short summaries."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "account_id": {"type": "string"},
                    "lookback_days": {"type": "integer", "minimum": 1, "maximum": 730},
                },
            },
        },
        {
            "name": "category_breakdown",
            "description": (
                "Expense totals grouped by category for one calendar month (aggregates only)."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "year_month": {
                        "type": "string",
                        "description": "YYYY-MM calendar month.",
                    },
                    "account_id": {"type": "string"},
                },
                "required": ["year_month"],
            },
        },
        {
            "name": "sql_select",
            "description": (
                "Read-only escape hatch: run a single SELECT (or WITH … SELECT) ending with "
                "LIMIT n where n ≤ 500. No writes."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "description": "Single SELECT … LIMIT … statement."},
                },
                "required": ["query"],
            },
        },
    ]


def tool_ledger_summary(*, account_id: str | None = None) -> dict[str, Any]:
    """Read-only aggregate over transactions (expenses positive in output)."""
    params: tuple[Any, ...]
    if account_id is None:
        sql = """
            SELECT COUNT(*)::bigint,
                   COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0)
            FROM transactions
        """
        params = ()
    else:
        UUID(account_id)
        sql = """
            SELECT COUNT(*)::bigint,
                   COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0)
            FROM transactions
            WHERE account_id = %s::uuid
        """
        params = (account_id,)

    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
    assert row is not None
    cnt = row[0]
    expense_abs = Decimal(row[1]).quantize(MONEY_PLACES)
    income_sum = Decimal(row[2]).quantize(MONEY_PLACES)
    return {
        "transaction_count": int(cnt),
        "expense_total_abs": str(expense_abs),
        "income_total": str(income_sum),
        "account_id": account_id,
    }


def tool_budget_status(*, year_month: str | None = None) -> dict[str, Any]:
    anchor = datetime.date.today()
    if year_month:
        month_start = parse_year_month(year_month)
    else:
        month_start = datetime.date(anchor.year, anchor.month, 1)
    with connect() as conn:
        rows = budget_status(conn, month_start, anchor)
    return {
        "year_month": f"{month_start.year}-{month_start.month:02d}",
        "as_of": anchor.isoformat(),
        "lines": [
            {
                "slug": r["slug"],
                "name": r["name"],
                "budget_amount": str(r["budget_amount"]),
                "spent_mtd": str(r["spent_mtd"]),
                "projected_spend": str(r["projected_spend"]),
                "remaining_mtd": str(r["remaining_mtd"]),
            }
            for r in rows
        ],
    }


def tool_cashflow_monthly(*, months: int = 6, account_id: str | None = None) -> dict[str, Any]:
    if months < 1 or months > 36:
        raise ValueError("months must be between 1 and 36")
    today = datetime.date.today()
    start_month = datetime.date(today.year, today.month, 1)
    for _ in range(months - 1):
        if start_month.month == 1:
            start_month = datetime.date(start_month.year - 1, 12, 1)
        else:
            start_month = datetime.date(start_month.year, start_month.month - 1, 1)

    params: tuple[Any, ...]
    if account_id is None:
        sql = """
            SELECT date_trunc('month', transaction_date)::date AS month,
                   COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) AS expenses,
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income
            FROM transactions
            WHERE transaction_date >= %s
            GROUP BY 1
            ORDER BY 1 DESC
        """
        params = (start_month,)
    else:
        UUID(account_id)
        sql = """
            SELECT date_trunc('month', transaction_date)::date AS month,
                   COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) AS expenses,
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income
            FROM transactions
            WHERE account_id = %s::uuid AND transaction_date >= %s
            GROUP BY 1
            ORDER BY 1 DESC
        """
        params = (account_id, start_month)

    out: list[dict[str, str]] = []
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    for r in rows:
        out.append(
            {
                "month": r[0].isoformat(),
                "expenses_abs": str(Decimal(r[1]).quantize(MONEY_PLACES)),
                "income": str(Decimal(r[2]).quantize(MONEY_PLACES)),
            }
        )
    return {"months_requested": months, "series": out, "account_id": account_id}


def _load_expense_rows(account_id: str | None) -> list[TxRow]:
    with connect() as conn:
        if account_id is None:
            rows = conn.execute(
                """
                SELECT id, transaction_date, amount, description_normalized, category_id
                FROM transactions
                WHERE amount < 0
                ORDER BY transaction_date
                """
            ).fetchall()
        else:
            UUID(account_id)
            rows = conn.execute(
                """
                SELECT id, transaction_date, amount, description_normalized, category_id
                FROM transactions
                WHERE account_id = %s::uuid AND amount < 0
                ORDER BY transaction_date
                """,
                (account_id,),
            ).fetchall()
    return [
        TxRow(
            id=str(r[0]),
            transaction_date=r[1],
            amount=r[2],
            description_normalized=r[3],
            category_id=str(r[4]) if r[4] is not None else None,
        )
        for r in rows
    ]


def tool_recurring_highlights(
    *,
    account_id: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    if limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25")
    txs = _load_expense_rows(account_id)
    series = detect_recurring(txs, min_occurrences=3)
    trimmed = series[:limit]
    return {
        "account_id": account_id,
        "items": [
            {
                "merchant": s.merchant,
                "typical_amount": str(s.typical_amount),
                "occurrences": s.occurrences,
                "first_seen": s.first_seen.isoformat(),
                "last_seen": s.last_seen.isoformat(),
            }
            for s in trimmed
        ],
    }


def tool_anomalies_summary(
    *,
    account_id: str | None = None,
    lookback_days: int = 120,
) -> dict[str, Any]:
    aid = UUID(account_id) if account_id else None
    anchor = datetime.date.today()
    window_start = anchor - datetime.timedelta(days=lookback_days)
    with connect() as conn:
        txs, first_seen = load_expense_window_and_first_seen(
            conn,
            account_id=aid,
            window_start=window_start,
            anchor=anchor,
        )
    signals = detect_anomalies(
        txs,
        as_of=anchor,
        lookback_days=lookback_days,
        first_seen_by_merchant=first_seen,
    )
    counts: dict[str, int] = {}
    for s in signals:
        counts[s.kind] = counts.get(s.kind, 0) + 1
    previews = [
        {
            "kind": s.kind,
            "merchant": s.merchant,
            "detail": s.detail,
            "transaction_date": s.transaction_date.isoformat(),
        }
        for s in signals[:12]
    ]
    return {
        "as_of": anchor.isoformat(),
        "lookback_days": lookback_days,
        "account_id": account_id,
        "counts_by_kind": counts,
        "preview": previews,
        "total_signals": len(signals),
    }


def tool_category_breakdown(*, year_month: str, account_id: str | None = None) -> dict[str, Any]:
    month_start = parse_year_month(year_month)
    if month_start.month == 12:
        month_end = datetime.date(month_start.year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        month_end = datetime.date(month_start.year, month_start.month + 1, 1) - datetime.timedelta(
            days=1
        )

    params: tuple[Any, ...]
    if account_id is None:
        sql = """
            SELECT c.slug, c.name,
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 0) AS spent
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
            WHERE t.transaction_date >= %s AND t.transaction_date <= %s
            GROUP BY c.slug, c.name
            HAVING COALESCE(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 0) > 0
            ORDER BY spent DESC
            LIMIT 50
        """
        params = (month_start, month_end)
    else:
        UUID(account_id)
        sql = """
            SELECT c.slug, c.name,
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 0) AS spent
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
            WHERE t.account_id = %s::uuid
              AND t.transaction_date >= %s AND t.transaction_date <= %s
            GROUP BY c.slug, c.name
            HAVING COALESCE(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 0) > 0
            ORDER BY spent DESC
            LIMIT 50
        """
        params = (account_id, month_start, month_end)

    lines: list[dict[str, str]] = []
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    for slug, name, spent in rows:
        lines.append(
            {"slug": slug, "name": name, "spent_abs": str(Decimal(spent).quantize(MONEY_PLACES))}
        )
    return {"year_month": year_month, "account_id": account_id, "lines": lines}


def _validate_sql_select(query: str) -> str:
    q = query.strip().rstrip(";")
    if ";" in q:
        raise ValueError("only one statement is allowed; remove semicolons")
    if _SQL_FORBIDDEN.search(q):
        raise ValueError("query contains a disallowed keyword for read-only mode")
    if not re.match(r"^\s*(WITH|SELECT)\b", q, re.IGNORECASE):
        raise ValueError("only SELECT (or WITH … SELECT) queries are allowed")
    lim = re.search(r"\blimit\s+(\d+)\s*$", q, re.IGNORECASE)
    if not lim:
        raise ValueError("query must end with LIMIT n (n ≤ 500)")
    n = int(lim.group(1))
    if n < 1 or n > 500:
        raise ValueError("LIMIT must be between 1 and 500")
    return q


def tool_sql_select(*, query: str) -> dict[str, Any]:
    q = _validate_sql_select(query)
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q)
            rows = cur.fetchall()
    cols = list(rows[0].keys()) if rows else []
    return {
        "row_count": len(rows),
        "columns": cols,
        "rows": [dict(r) for r in rows],
    }


def invoke_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch read-only tools; mutating operations are not implemented."""
    if name == "ledger_summary":
        aid = arguments.get("account_id")
        if aid is not None and not isinstance(aid, str):
            raise TypeError("account_id must be a string UUID or omitted")
        return tool_ledger_summary(account_id=aid)

    if name == "budget_status":
        ym = arguments.get("year_month")
        if ym is not None and not isinstance(ym, str):
            raise TypeError("year_month must be a string or omitted")
        try:
            return tool_budget_status(year_month=ym)
        except BudgetServiceError as e:
            raise ValueError(str(e)) from e

    if name == "cashflow_monthly":
        months = arguments.get("months", 6)
        aid = arguments.get("account_id")
        if not isinstance(months, int):
            raise TypeError("months must be an integer")
        if aid is not None and not isinstance(aid, str):
            raise TypeError("account_id must be a string UUID or omitted")
        return tool_cashflow_monthly(months=months, account_id=aid)

    if name == "recurring_highlights":
        aid = arguments.get("account_id")
        lim = arguments.get("limit", 8)
        if aid is not None and not isinstance(aid, str):
            raise TypeError("account_id must be a string UUID or omitted")
        if not isinstance(lim, int):
            raise TypeError("limit must be an integer")
        return tool_recurring_highlights(account_id=aid, limit=lim)

    if name == "anomalies_summary":
        aid = arguments.get("account_id")
        lb = arguments.get("lookback_days", 120)
        if aid is not None and not isinstance(aid, str):
            raise TypeError("account_id must be a string UUID or omitted")
        if not isinstance(lb, int):
            raise TypeError("lookback_days must be an integer")
        return tool_anomalies_summary(account_id=aid, lookback_days=lb)

    if name == "category_breakdown":
        ym = arguments.get("year_month")
        aid = arguments.get("account_id")
        if not isinstance(ym, str):
            raise TypeError("year_month is required")
        if aid is not None and not isinstance(aid, str):
            raise TypeError("account_id must be a string UUID or omitted")
        try:
            return tool_category_breakdown(year_month=ym, account_id=aid)
        except BudgetServiceError as e:
            raise ValueError(str(e)) from e

    if name == "sql_select":
        q = arguments.get("query")
        if not isinstance(q, str):
            raise TypeError("query must be a string")
        return tool_sql_select(query=q)

    raise ValueError(f"unknown tool: {name}")
