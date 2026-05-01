"""Anomaly signals — unit tests (pure) + HTTP integration."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest

from pfa.anomalies import detect_anomalies, expense_first_seen_by_merchant
from pfa.recurring import TxRow


def _tx(desc: str, date: datetime.date, amount: str = "-10.00", tid: str | None = None) -> TxRow:
    return TxRow(
        id=tid or str(uuid.uuid4()),
        transaction_date=date,
        amount=Decimal(amount),
        description_normalized=desc,
        category_id=None,
    )


def test_large_spend_flags_outlier_vs_median():
    txs = [
        _tx("cafe", datetime.date(2025, 3, 1), "-10"),
        _tx("cafe", datetime.date(2025, 3, 5), "-10"),
        _tx("cafe", datetime.date(2025, 3, 10), "-10"),
        _tx("cafe", datetime.date(2025, 3, 15), "-40"),
    ]
    fs = expense_first_seen_by_merchant(txs)
    out = detect_anomalies(
        txs,
        as_of=datetime.date(2025, 3, 20),
        lookback_days=90,
        first_seen_by_merchant=fs,
    )
    kinds = {s.kind for s in out}
    assert "large_spend" in kinds
    large = [s for s in out if s.kind == "large_spend"]
    assert len(large) == 1
    assert large[0].merchant == "cafe"
    assert large[0].amount == Decimal("-40")


def test_new_merchant_within_window():
    txs = [_tx("brand_new_shop", datetime.date(2025, 6, 1), "-25")]
    fs = expense_first_seen_by_merchant(txs)
    out = detect_anomalies(
        txs,
        as_of=datetime.date(2025, 6, 10),
        lookback_days=90,
        first_seen_by_merchant=fs,
        new_merchant_days=30,
    )
    assert any(s.kind == "new_merchant" for s in out)


def test_new_merchant_old_first_seen_not_flagged():
    full = [
        _tx("old_shop", datetime.date(2024, 1, 1), "-5"),
        _tx("old_shop", datetime.date(2025, 6, 1), "-5"),
    ]
    fs = expense_first_seen_by_merchant(full)
    anchor = datetime.date(2025, 6, 10)
    window_start = anchor - datetime.timedelta(days=120)
    in_window = [t for t in full if window_start <= t.transaction_date <= anchor]
    out = detect_anomalies(
        in_window,
        as_of=anchor,
        lookback_days=120,
        first_seen_by_merchant=fs,
        new_merchant_days=14,
    )
    assert not any(s.kind == "new_merchant" and s.merchant == "old_shop" for s in out)


def test_monthly_spike_vs_prior_median():
    txs = [
        _tx("utilities", datetime.date(2025, 1, 31), "-100"),
        _tx("utilities", datetime.date(2025, 2, 28), "-100"),
        _tx("utilities", datetime.date(2025, 3, 31), "-100"),
        _tx("utilities", datetime.date(2025, 4, 15), "-400"),
    ]
    fs = expense_first_seen_by_merchant(txs)
    out = detect_anomalies(
        txs,
        as_of=datetime.date(2025, 4, 30),
        lookback_days=200,
        first_seen_by_merchant=fs,
        monthly_spike_ratio=Decimal("2"),
    )
    spikes = [s for s in out if s.kind == "monthly_spike"]
    assert len(spikes) == 1
    assert spikes[0].merchant == "utilities"
    assert spikes[0].amount == Decimal("-400")


def test_detect_anomalies_validates_lookback():
    with pytest.raises(ValueError, match="lookback_days"):
        detect_anomalies(
            [],
            as_of=datetime.date.today(),
            lookback_days=0,
            first_seen_by_merchant={},
        )


@pytest.mark.integration
def test_get_anomalies_http_large_spend(client, sample_account_id, clean_db):
    aid = str(sample_account_id)
    rows = [
        ("cafe", datetime.date(2025, 3, 1), "-10"),
        ("cafe", datetime.date(2025, 3, 5), "-10"),
        ("cafe", datetime.date(2025, 3, 10), "-10"),
        ("cafe", datetime.date(2025, 3, 15), "-40"),
    ]
    with clean_db.cursor() as cur:
        for desc, d, amt in rows:
            cur.execute(
                """
                INSERT INTO transactions (
                  account_id, transaction_date, amount, currency,
                  description_raw, description_normalized, dedupe_fingerprint
                ) VALUES (%s, %s, %s, 'USD', %s, %s, %s)
                """,
                (aid, d, amt, desc, desc, f"fp-{uuid.uuid4()}"),
            )
    clean_db.commit()

    r = client.get(
        "/anomalies",
        params={
            "account_id": aid,
            "as_of": "2025-03-20",
            "lookback_days": 90,
        },
    )
    assert r.status_code == 200
    body = r.json()
    kinds = {x["kind"] for x in body}
    assert "large_spend" in kinds


@pytest.mark.integration
def test_get_anomalies_rejects_invalid_lookback(client, sample_account_id):
    r = client.get(
        "/anomalies",
        params={"account_id": str(sample_account_id), "lookback_days": 0},
    )
    assert r.status_code == 422
