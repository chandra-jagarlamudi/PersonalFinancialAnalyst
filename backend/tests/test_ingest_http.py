"""HTTP ingest behavior against real Postgres."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


def test_ingest_csv_inserts_then_skips_duplicates(client, sample_account_id):
    csv = (
        "transaction_date,amount,description\n"
        "2025-03-01,-12.34,GROCERY\n"
        "2025-03-02,100.00,PAYROLL\n"
    ).encode()
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(sample_account_id)},
        files={"file": ("stmt.csv", csv, "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"inserted": 2, "skipped_duplicates": 0}
    r2 = client.post(
        "/ingest/csv",
        data={"account_id": str(sample_account_id)},
        files={"file": ("stmt.csv", csv, "text/csv")},
    )
    assert r2.status_code == 200
    assert r2.json() == {"inserted": 0, "skipped_duplicates": 2}


def test_ingest_unknown_account_returns_404(client, clean_db):
    csv = b"transaction_date,amount,description\n2025-03-01,-1,X\n"
    missing = uuid.uuid4()
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(missing)},
        files={"file": ("stmt.csv", csv, "text/csv")},
    )
    assert r.status_code == 404


def test_ingest_invalid_csv_returns_422(client, sample_account_id):
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(sample_account_id)},
        files={
            "file": (
                "bad.csv",
                b"transaction_date,description\n2025-03-01,X\n",
                "text/csv",
            )
        },
    )
    assert r.status_code == 422


def test_ingest_csv_over_max_size_returns_413(client, sample_account_id, monkeypatch):
    from pfa import main

    monkeypatch.setattr(main, "MAX_CSV_UPLOAD_BYTES", 64)
    payload = b"x" * 65
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(sample_account_id)},
        files={"file": ("big.csv", payload, "text/csv")},
    )
    assert r.status_code == 413
