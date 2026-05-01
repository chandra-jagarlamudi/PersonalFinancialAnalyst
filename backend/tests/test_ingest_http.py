"""HTTP ingest behavior against real Postgres."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

_CSV = (
    "transaction_date,amount,description\n"
    "2025-03-01,-12.34,GROCERY\n"
    "2025-03-02,100.00,PAYROLL\n"
).encode()


def _post_csv(client, account_id, csv_bytes=None, filename="stmt.csv"):
    return client.post(
        "/ingest/csv",
        data={"account_id": str(account_id)},
        files={"file": (filename, csv_bytes or _CSV, "text/csv")},
    )


def test_ingest_csv_inserts_and_returns_statement_id(client, sample_account_id, upload_dir):
    r = _post_csv(client, sample_account_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 2
    assert body["skipped_duplicates"] == 0
    assert "statement_id" in body
    assert body["duplicate_statement"] is False


def test_transaction_level_dedupe_skips_on_second_ingest(client, sample_account_id, upload_dir):
    _post_csv(client, sample_account_id)
    r2 = _post_csv(client, sample_account_id, csv_bytes=b"transaction_date,amount,description\n2025-03-01,-12.34,GROCERY\n")
    assert r2.status_code == 200
    assert r2.json()["skipped_duplicates"] == 1


def test_hash_idempotency_returns_duplicate_flag(client, sample_account_id, upload_dir):
    r1 = _post_csv(client, sample_account_id)
    assert r1.status_code == 200
    sid1 = r1.json()["statement_id"]

    r2 = _post_csv(client, sample_account_id)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["duplicate_statement"] is True
    assert body2["statement_id"] == sid1
    assert body2["inserted"] == 2
    assert body2["skipped_duplicates"] == 0


def test_purge_deletes_statement_and_transactions(client, sample_account_id, upload_dir):
    r = _post_csv(client, sample_account_id)
    sid = r.json()["statement_id"]

    del_r = client.delete(f"/statements/{sid}")
    assert del_r.status_code == 204

    # Re-ingest same file must succeed (record gone) and not be flagged as duplicate.
    r2 = _post_csv(client, sample_account_id)
    assert r2.status_code == 200
    assert r2.json()["duplicate_statement"] is False
    assert r2.json()["inserted"] == 2


def test_purge_unknown_statement_returns_404(client, clean_db, upload_dir):
    r = client.delete(f"/statements/{uuid.uuid4()}")
    assert r.status_code == 404


def test_ingest_unknown_account_returns_404(client, clean_db, upload_dir):
    r = _post_csv(client, uuid.uuid4())
    assert r.status_code == 404


def test_ingest_invalid_csv_returns_422(client, sample_account_id, upload_dir):
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(sample_account_id)},
        files={"file": ("bad.csv", b"transaction_date,description\n2025-03-01,X\n", "text/csv")},
    )
    assert r.status_code == 422


def test_same_file_under_different_account_is_not_a_duplicate(client, clean_db, upload_dir):
    # Create two separate accounts.
    iid = uuid.uuid4()
    aid1, aid2 = uuid.uuid4(), uuid.uuid4()
    with clean_db.cursor() as cur:
        cur.execute("INSERT INTO institutions (id, name) VALUES (%s, %s)", (str(iid), "Bank"))
        for aid in (aid1, aid2):
            cur.execute(
                "INSERT INTO accounts (id, institution_id, name, currency) VALUES (%s, %s, %s, %s)",
                (str(aid), str(iid), "Checking", "USD"),
            )
    clean_db.commit()

    r1 = _post_csv(client, aid1)
    assert r1.status_code == 200
    assert r1.json()["duplicate_statement"] is False

    r2 = _post_csv(client, aid2)
    assert r2.status_code == 200
    assert r2.json()["duplicate_statement"] is False
    assert r2.json()["inserted"] == 2
    assert r2.json()["statement_id"] != r1.json()["statement_id"]


def test_ingest_csv_over_max_size_returns_413(client, sample_account_id, monkeypatch, upload_dir):
    from pfa import main
    monkeypatch.setattr(main, "MAX_CSV_UPLOAD_BYTES", 64)
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(sample_account_id)},
        files={"file": ("big.csv", b"x" * 65, "text/csv")},
    )
    assert r.status_code == 413
