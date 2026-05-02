"""Async ingest job HTTP API tests."""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

pytestmark = pytest.mark.integration


def _setup_account(client) -> str:
    institution = client.post("/institutions", json={"name": "Queue Bank"}).json()
    account = client.post(
        "/accounts",
        json={
            "institution_id": institution["id"],
            "name": "Checking",
            "currency": "USD",
        },
    ).json()
    return account["id"]


_VALID_CSV = (
    b"transaction_date,amount,description\n"
    b"2025-03-01,-12.34,GROCERY\n"
    b"2025-03-02,-9.99,COFFEE\n"
)


def test_csv_job_persists_statement_and_transactions(client, db_conn, upload_dir):
    account_id = _setup_account(client)
    response = client.post(
        "/ingest/jobs/csv",
        data={"account_id": account_id},
        files={"file": ("sample.csv", _VALID_CSV, "text/csv")},
    )

    assert response.status_code == 202
    job_id = response.json()["id"]

    job = client.get(f"/ingest/jobs/{job_id}")
    assert job.status_code == 200
    body = job.json()
    assert body["status"] == "succeeded"
    assert body["parsed_rows"] == 2
    assert body["inserted_rows"] == 2
    assert body["skipped_duplicates"] == 0
    assert body["statement_id"] is not None
    assert [step["step_key"] for step in body["steps"]] == [
        "extract",
        "normalize",
        "dedupe",
        "categorize",
        "persist",
    ]
    assert body["steps"][-1]["detail"] == "statement and transactions persisted to the ledger"

    with db_conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT inserted, skipped_duplicates FROM statements WHERE id = %s",
            (body["statement_id"],),
        )
        statement = cur.fetchone()
    assert statement == {"inserted": 2, "skipped_duplicates": 0}

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM transactions WHERE source_statement_id = %s",
            (body["statement_id"],),
        )
        tx_count = cur.fetchone()[0]
    assert tx_count == 2


def test_duplicate_csv_job_reuses_existing_statement(client, db_conn, upload_dir):
    account_id = _setup_account(client)
    payload = {
        "data": {"account_id": account_id},
        "files": {"file": ("sample.csv", _VALID_CSV, "text/csv")},
    }

    first = client.post("/ingest/jobs/csv", **payload)
    second = client.post("/ingest/jobs/csv", **payload)

    assert first.status_code == 202
    assert second.status_code == 202

    first_job = client.get(f"/ingest/jobs/{first.json()['id']}").json()
    second_job = client.get(f"/ingest/jobs/{second.json()['id']}").json()

    assert first_job["statement_id"] == second_job["statement_id"]
    assert second_job["inserted_rows"] == 2
    assert second_job["skipped_duplicates"] == 0
    assert second_job["steps"][-1]["detail"] == "statement already ingested; reused existing ledger rows"

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM statements WHERE account_id = %s",
            (account_id,),
        )
        statement_count = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM transactions WHERE source_statement_id = %s",
            (first_job["statement_id"],),
        )
        transaction_count = cur.fetchone()[0]
    assert statement_count == 1
    assert transaction_count == 2


def test_failed_job_can_retry(client, upload_dir):
    account_id = _setup_account(client)
    response = client.post(
        "/ingest/jobs/csv",
        data={"account_id": account_id},
        files={"file": ("bad.csv", b"transaction_date,description\n2025-03-01,X\n", "text/csv")},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    failed = client.get(f"/ingest/jobs/{job_id}").json()
    assert failed["status"] == "failed"

    retried = client.post(f"/ingest/jobs/{job_id}/retry")
    assert retried.status_code == 200
    retried_body = client.get(f"/ingest/jobs/{job_id}").json()
    assert retried_body["retry_count"] == 1
    assert retried_body["status"] == "failed"
