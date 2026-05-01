"""Deterministic recurring charge detection (slice 8)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TxRow:
    id: str
    transaction_date: datetime.date
    amount: Decimal
    description_normalized: str
    category_id: str | None


@dataclass
class RecurringCandidate:
    merchant: str
    typical_amount: Decimal
    occurrences: int
    first_seen: datetime.date
    last_seen: datetime.date
    monthly_dates: list[datetime.date]
    category_id: str | None


def _decimal_median(values: list[Decimal]) -> Decimal:
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def detect_recurring(transactions: list[TxRow], min_occurrences: int = 3) -> list[RecurringCandidate]:
    if min_occurrences < 3:
        raise ValueError("min_occurrences must be at least 3 (monthly recurring threshold)")
    groups: dict[str, list[TxRow]] = {}
    for tx in transactions:
        groups.setdefault(tx.description_normalized, []).append(tx)

    candidates: list[RecurringCandidate] = []
    for merchant, txs in groups.items():
        if len(txs) < min_occurrences:
            continue

        sorted_txs = sorted(txs, key=lambda t: t.transaction_date)

        cadence_ok = True
        for i in range(1, len(sorted_txs)):
            delta = (sorted_txs[i].transaction_date - sorted_txs[i - 1].transaction_date).days
            if not (25 <= delta <= 35):
                cadence_ok = False
                break
        if not cadence_ok:
            continue

        amounts = [t.amount for t in sorted_txs]
        median_amt = _decimal_median(amounts)
        median_abs = abs(median_amt)
        lower = median_abs * Decimal("0.9")
        upper = median_abs * Decimal("1.1")
        if not all(lower <= abs(a) <= upper for a in amounts):
            continue

        candidates.append(
            RecurringCandidate(
                merchant=merchant,
                typical_amount=median_amt,
                occurrences=len(sorted_txs),
                first_seen=sorted_txs[0].transaction_date,
                last_seen=sorted_txs[-1].transaction_date,
                monthly_dates=[t.transaction_date for t in sorted_txs],
                category_id=sorted_txs[-1].category_id,
            )
        )

    candidates.sort(key=lambda c: (-c.occurrences, c.merchant))
    return candidates
