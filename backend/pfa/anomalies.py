"""Deterministic anomaly signals (slice 9) — PRD: spikes, new merchants, large txns."""

from __future__ import annotations

import calendar
import datetime
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from pfa.recurring import TxRow


def load_expense_window_and_first_seen(
    conn,
    *,
    account_id: UUID | None,
    window_start: datetime.date,
    anchor: datetime.date,
) -> tuple[list[TxRow], dict[str, datetime.date]]:
    """Ledger expense rows in [window_start, anchor] plus first-ever spend date per merchant in-window."""
    if account_id is not None:
        aid = str(account_id)
        rows = conn.execute(
            """
            SELECT id, transaction_date, amount, description_normalized, category_id
            FROM transactions
            WHERE account_id = %s::uuid
              AND amount < 0
              AND transaction_date >= %s
              AND transaction_date <= %s
            ORDER BY transaction_date
            """,
            (aid, window_start, anchor),
        ).fetchall()
        first_seen_rows = conn.execute(
            """
            WITH mer AS (
              SELECT DISTINCT description_normalized AS d
              FROM transactions
              WHERE account_id = %s::uuid
                AND amount < 0
                AND transaction_date >= %s
                AND transaction_date <= %s
            )
            SELECT t.description_normalized, MIN(t.transaction_date)
            FROM transactions t
            INNER JOIN mer ON mer.d = t.description_normalized
            WHERE t.account_id = %s::uuid AND t.amount < 0
            GROUP BY t.description_normalized
            """,
            (aid, window_start, anchor, aid),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, transaction_date, amount, description_normalized, category_id
            FROM transactions
            WHERE amount < 0
              AND transaction_date >= %s
              AND transaction_date <= %s
            ORDER BY transaction_date
            """,
            (window_start, anchor),
        ).fetchall()
        first_seen_rows = conn.execute(
            """
            WITH mer AS (
              SELECT DISTINCT description_normalized AS d
              FROM transactions
              WHERE amount < 0
                AND transaction_date >= %s
                AND transaction_date <= %s
            )
            SELECT t.description_normalized, MIN(t.transaction_date)
            FROM transactions t
            INNER JOIN mer ON mer.d = t.description_normalized
            WHERE t.amount < 0
            GROUP BY t.description_normalized
            """,
            (window_start, anchor),
        ).fetchall()

    txs = [
        TxRow(
            id=str(r[0]),
            transaction_date=r[1],
            amount=r[2],
            description_normalized=r[3],
            category_id=str(r[4]) if r[4] is not None else None,
        )
        for r in rows
    ]
    first_seen: dict[str, datetime.date] = {str(r[0]): r[1] for r in first_seen_rows}
    return txs, first_seen


def expense_first_seen_by_merchant(expense_rows: list[TxRow]) -> dict[str, datetime.date]:
    """Earliest expense date per merchant from the given rows (full-history scope for that query)."""
    out: dict[str, datetime.date] = {}
    for t in sorted((x for x in expense_rows if x.amount < 0), key=lambda x: x.transaction_date):
        m = t.description_normalized
        if m not in out:
            out[m] = t.transaction_date
    return out


@dataclass
class AnomalySignal:
    kind: str  # large_spend | new_merchant | monthly_spike
    merchant: str
    detail: str
    transaction_id: str | None
    transaction_date: datetime.date
    amount: Decimal | None


def _median_abs(values: list[Decimal]) -> Decimal:
    absv = sorted(abs(x) for x in values)
    n = len(absv)
    if n == 0:
        return Decimal("0")
    mid = n // 2
    if n % 2 == 1:
        return absv[mid]
    return (absv[mid - 1] + absv[mid]) / 2


def _month_totals_by_merchant(
    txs: list[TxRow],
) -> dict[str, dict[tuple[int, int], Decimal]]:
    """Merchant -> (year, month) -> sum of spending (positive number = amount spent)."""
    out: dict[str, dict[tuple[int, int], Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    for t in txs:
        if t.amount >= 0:
            continue
        mk = (t.transaction_date.year, t.transaction_date.month)
        out[t.description_normalized][mk] += abs(t.amount)
    return out


def detect_anomalies(
    expenses_in_window: list[TxRow],
    *,
    as_of: datetime.date,
    lookback_days: int = 120,
    first_seen_by_merchant: dict[str, datetime.date],
    large_vs_median_multiplier: Decimal = Decimal("3"),
    new_merchant_days: int = 14,
    monthly_spike_ratio: Decimal = Decimal("2"),
    min_months_for_spike: int = 4,
) -> list[AnomalySignal]:
    if lookback_days < 1:
        raise ValueError("lookback_days must be >= 1")
    if large_vs_median_multiplier < Decimal("1"):
        raise ValueError("large_vs_median_multiplier must be >= 1")
    if new_merchant_days < 1:
        raise ValueError("new_merchant_days must be >= 1")

    expenses = [t for t in expenses_in_window if t.amount < 0]

    signals: list[AnomalySignal] = []
    by_merchant: dict[str, list[TxRow]] = defaultdict(list)
    for t in expenses:
        by_merchant[t.description_normalized].append(t)

    for merchant, txs_m in by_merchant.items():
        txs_m = sorted(txs_m, key=lambda x: x.transaction_date)
        fs = first_seen_by_merchant.get(merchant)
        if fs is not None and (as_of - fs).days <= new_merchant_days:
            signals.append(
                AnomalySignal(
                    kind="new_merchant",
                    merchant=merchant,
                    detail=f"first spend {fs.isoformat()} within {new_merchant_days}d of as_of",
                    transaction_id=txs_m[0].id,
                    transaction_date=txs_m[0].transaction_date,
                    amount=txs_m[0].amount,
                )
            )

        if len(txs_m) >= 2:
            med = _median_abs([t.amount for t in txs_m])
            floor = max(med, Decimal("0.01"))
            for t in txs_m:
                if abs(t.amount) > large_vs_median_multiplier * floor:
                    signals.append(
                        AnomalySignal(
                            kind="large_spend",
                            merchant=merchant,
                            detail=f"|amount| {abs(t.amount)} > {large_vs_median_multiplier}×median_abs {med:.4f}",
                            transaction_id=t.id,
                            transaction_date=t.transaction_date,
                            amount=t.amount,
                        )
                    )

    month_totals = _month_totals_by_merchant(expenses)
    for merchant, months in month_totals.items():
        if len(months) < min_months_for_spike:
            continue
        keys_sorted = sorted(months.keys())
        last_key = keys_sorted[-1]
        last_total = months[last_key]
        prior_keys = keys_sorted[:-1]
        if len(prior_keys) < min_months_for_spike - 1:
            continue
        prior_vals = [months[k] for k in prior_keys]
        prior_med = _median_abs(prior_vals)  # median of positive month totals
        if prior_med <= 0:
            continue
        if last_total > monthly_spike_ratio * prior_med:
            y, mo = last_key
            last_day = calendar.monthrange(y, mo)[1]
            signals.append(
                AnomalySignal(
                    kind="monthly_spike",
                    merchant=merchant,
                    detail=(
                        f"{y}-{mo:02d}: monthly expense magnitude (sum of abs amounts) "
                        f"{last_total} > {monthly_spike_ratio}×prior median {prior_med:.4f}; "
                        f"amount uses ledger convention (negative = outflow, abs matches magnitude)"
                    ),
                    transaction_id=None,
                    transaction_date=datetime.date(y, mo, last_day),
                    amount=-last_total,
                )
            )

    signals.sort(key=lambda s: (s.transaction_date, s.kind, s.merchant), reverse=True)
    return signals
