"""T-058: Compact CSV formatter for transaction context passed to Claude.

Serializes transactions as header + data rows to minimize token count.
Truncates to most recent N if over budget. Logs warning near limit.
"""

from __future__ import annotations

import csv
import io
import math
from decimal import Decimal
from typing import Any

import structlog

log = structlog.get_logger()

_DEFAULT_MAX_ROWS = 2000
# ~4 chars per token rough estimate for CSV content
_CHARS_PER_TOKEN = 4
_WARN_THRESHOLD = 0.80  # warn at 80% of max rows


def format_transactions_csv(
    transactions: list[Any],
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> tuple[str, int]:
    """Return (csv_string, estimated_token_count).

    Truncates to most recent `max_rows` if over budget.
    Transactions should have .date, .description, .amount, .transaction_type, .category attrs.
    """
    total = len(transactions)
    if total >= math.ceil(_WARN_THRESHOLD * max_rows):
        log.warning(
            "context_formatter.near_limit",
            transaction_count=total,
            max_rows=max_rows,
        )

    # Most recent first — sort descending by date
    sorted_txns = sorted(transactions, key=lambda t: t.date, reverse=True)
    rows_to_use = sorted_txns[:max_rows]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "description", "amount", "type", "category"])
    for txn in rows_to_use:
        # Plain decimal, no currency symbol
        amount = txn.amount
        if isinstance(amount, Decimal):
            amount_str = str(amount)
        else:
            amount_str = f"{float(amount):.2f}"
        writer.writerow([
            str(txn.date),
            txn.description,
            amount_str,
            txn.transaction_type,
            txn.category or "",
        ])

    csv_text = buf.getvalue()
    estimated_tokens = max(1, len(csv_text) // _CHARS_PER_TOKEN)
    return csv_text, estimated_tokens
