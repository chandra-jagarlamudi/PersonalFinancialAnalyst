"""HTTP integration tests for the recurring charges endpoint."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

_RECURRING_CSV = (
    b"transaction_date,amount,description\n"
    b"2025-01-01,-9.99,NETFLIX\n"
    b"2025-02-01,-9.99,NETFLIX\n"
    b"2025-03-01,-9.99,NETFLIX\n"
    b"2025-01-15,-50.00,GROCERY STORE\n"
)


def _ingest(client, account_id, csv_bytes, upload_dir):
    return client.post(
        "/ingest/csv",
        data={"account_id": str(account_id)},
        files={"file": ("stmt.csv", csv_bytes, "text/csv")},
    )


def test_list_recurring_empty(client, sample_account_id):
    r = client.get("/recurring", params={"account_id": str(sample_account_id)})
    assert r.status_code == 200
    assert r.json() == []


def test_list_recurring_after_ingest(client, sample_account_id, upload_dir):
    ingest_r = _ingest(client, sample_account_id, _RECURRING_CSV, upload_dir)
    assert ingest_r.status_code == 200, ingest_r.text

    r = client.get("/recurring", params={"account_id": str(sample_account_id)})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    item = body[0]
    assert "NETFLIX" in item["merchant"].upper()
    assert item["occurrences"] == 3


def test_list_recurring_account_filter(client, sample_account_id, upload_dir):
    _ingest(client, sample_account_id, _RECURRING_CSV, upload_dir)

    r = client.get("/recurring", params={"account_id": str(sample_account_id)})
    assert r.status_code == 200
    assert len(r.json()) == 1

    other_account_id = uuid.uuid4()
    r2 = client.get("/recurring", params={"account_id": str(other_account_id)})
    assert r2.status_code == 200
    assert r2.json() == []


def test_list_recurring_min_occurrences_filter(client, sample_account_id, upload_dir):
    _ingest(client, sample_account_id, _RECURRING_CSV, upload_dir)

    r = client.get(
        "/recurring",
        params={"account_id": str(sample_account_id), "min_occurrences": 4},
    )
    assert r.status_code == 200
    assert r.json() == []
