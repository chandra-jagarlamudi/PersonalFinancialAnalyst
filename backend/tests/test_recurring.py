"""Recurring charge detection — unit tests (pure) + HTTP integration."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest

from pfa.recurring import RecurringCandidate, TxRow, detect_recurring


def _tx(desc: str, date: datetime.date, amount: str = "-15.99", category_id=None) -> TxRow:
    return TxRow(
        id=str(uuid.uuid4()),
        transaction_date=date,
        amount=Decimal(amount),
        description_normalized=desc,
        category_id=category_id,
    )


def _monthly(desc: str, start: datetime.date, n: int, amount: str = "-15.99") -> list[TxRow]:
    txs = []
    d = start
    for _ in range(n):
        txs.append(_tx(desc, d, amount))
        d = d.replace(month=d.month % 12 + 1, year=d.year + (1 if d.month == 12 else 0))
    return txs


# ── Pure unit tests (no DB) ──────────────────────────────────────────────────

def test_monthly_detected():
    txs = _monthly("netflix", datetime.date(2024, 1, 15), 12)
    result = detect_recurring(txs)
    assert len(result) == 1
    assert result[0].merchant == "netflix"
    assert result[0].occurrences == 12
    assert result[0].typical_amount == Decimal("-15.99")


def test_two_charges_not_recurring():
    txs = _monthly("netflix", datetime.date(2024, 1, 15), 2)
    assert detect_recurring(txs) == []


def test_cadence_with_drift_detected():
    # Drift by 1 day each month — still within 25–35 window
    dates = [
        datetime.date(2024, 1, 1),
        datetime.date(2024, 2, 1),   # 31 days
        datetime.date(2024, 3, 3),   # 31 days
    ]
    txs = [_tx("spotify", d) for d in dates]
    result = detect_recurring(txs)
    assert len(result) == 1


def test_cadence_break_not_recurring():
    dates = [
        datetime.date(2025, 1, 1),
        datetime.date(2025, 2, 1),
        datetime.date(2025, 3, 1),
        datetime.date(2025, 6, 1),  # 92-day gap — breaks cadence
    ]
    txs = [_tx("hulu", d) for d in dates]
    assert detect_recurring(txs) == []


def test_amount_variance_too_high():
    dates = [
        datetime.date(2025, 1, 1),
        datetime.date(2025, 2, 1),
        datetime.date(2025, 3, 3),
    ]
    amounts = ["-100.00", "-100.00", "-130.00"]  # 130 is >10% above median 100
    txs = [_tx("gym", d, a) for d, a in zip(dates, amounts)]
    assert detect_recurring(txs) == []


def test_mixed_dataset_only_recurring_returned():
    recurring = _monthly("netflix", datetime.date(2024, 1, 15), 6)
    irregular = [
        _tx("random store", datetime.date(2024, 1, 5), "-42.00"),
        _tx("random store", datetime.date(2024, 4, 20), "-38.00"),
    ]
    result = detect_recurring(recurring + irregular)
    assert len(result) == 1
    assert result[0].merchant == "netflix"


def test_detect_recurring_rejects_min_occurrences_below_three():
    txs = _monthly("netflix", datetime.date(2024, 1, 15), 4)
    with pytest.raises(ValueError, match="min_occurrences"):
        detect_recurring(txs, min_occurrences=2)


# ── HTTP integration test ────────────────────────────────────────────────────


@pytest.mark.integration
def test_get_recurring_http(client, sample_account_id, clean_db):
    dates = [
        datetime.date(2024, 1, 15),
        datetime.date(2024, 2, 15),
        datetime.date(2024, 3, 16),
    ]
    with clean_db.cursor() as cur:
        for d in dates:
            cur.execute(
                """
                INSERT INTO transactions (
                  account_id, transaction_date, amount, currency,
                  description_raw, description_normalized, dedupe_fingerprint
                ) VALUES (%s, %s, %s, 'USD', 'Netflix', 'netflix', %s)
                """,
                (str(sample_account_id), d, "-15.99", f"fp-{uuid.uuid4()}"),
            )
    clean_db.commit()

    r = client.get("/recurring", params={"account_id": str(sample_account_id)})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["merchant"] == "netflix"
    assert body[0]["occurrences"] == 3


@pytest.mark.integration
def test_get_recurring_rejects_min_occurrences_below_three(client, sample_account_id):
    r = client.get(
        "/recurring",
        params={"account_id": str(sample_account_id), "min_occurrences": 2},
    )
    assert r.status_code == 422
