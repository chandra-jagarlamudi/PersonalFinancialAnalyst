"""Embedded MCP-shaped read tools (slice 10)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pfa.db import connect

MONEY_PLACES = Decimal("0.0001")


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
        }
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
        UUID(account_id)  # validate
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


def invoke_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "ledger_summary":
        aid = arguments.get("account_id")
        if aid is not None and not isinstance(aid, str):
            raise TypeError("account_id must be a string UUID or omitted")
        return tool_ledger_summary(account_id=aid)
    raise ValueError(f"unknown tool: {name}")
