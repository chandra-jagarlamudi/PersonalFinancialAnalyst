"""Statement listing and lifecycle tests (Slice 6)."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

_CSV = (
    "transaction_date,amount,description\n"
    "2025-01-01,-10.00,COFFEE\n"
    "2025-01-02,500.00,PAYROLL\n"
).encode()


def _upload(client, account_id, csv_bytes=None, filename="test.csv"):
    return client.post(
        "/ingest/csv",
        data={"account_id": str(account_id)},
        files={"file": (filename, csv_bytes or _CSV, "text/csv")},
    )


def test_list_statements_empty(client, sample_account_id, upload_dir):
    r = client.get(f"/statements?account_id={sample_account_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_list_statements_after_ingest(client, sample_account_id, upload_dir):
    ingest_r = _upload(client, sample_account_id, filename="bank.csv")
    assert ingest_r.status_code == 200
    sid = ingest_r.json()["statement_id"]

    r = client.get(f"/statements?account_id={sample_account_id}")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1

    item = items[0]
    assert item["id"] == sid
    assert item["account_id"] == str(sample_account_id)
    assert item["filename"] == "bank.csv"
    assert "sha256" in item
    assert item["inserted"] == 2
    assert item["skipped_duplicates"] == 0
    assert "byte_size" in item
    assert "created_at" in item


def test_get_statement_by_id(client, sample_account_id, upload_dir):
    ingest_r = _upload(client, sample_account_id)
    assert ingest_r.status_code == 200
    sid = ingest_r.json()["statement_id"]

    r = client.get(f"/statements/{sid}")
    assert r.status_code == 200
    item = r.json()
    assert item["id"] == sid
    assert item["account_id"] == str(sample_account_id)
    assert "filename" in item
    assert "sha256" in item


def test_get_statement_not_found(client, upload_dir):
    r = client.get(f"/statements/{uuid.uuid4()}")
    assert r.status_code == 404


def test_purge_statement_removes_it(client, sample_account_id, upload_dir):
    ingest_r = _upload(client, sample_account_id)
    assert ingest_r.status_code == 200
    sid = ingest_r.json()["statement_id"]

    uploaded_files = [path for path in upload_dir.rglob("*") if path.is_file()]
    assert uploaded_files, "expected uploaded raw bytes to be stored in upload_dir"

    del_r = client.delete(f"/statements/{sid}")
    assert del_r.status_code == 204

    r = client.get(f"/statements/{sid}")
    assert r.status_code == 404
    assert not any(path.is_file() for path in upload_dir.rglob("*"))
