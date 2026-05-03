"""Async ingest job HTTP API tests."""

from __future__ import annotations

import uuid

import pytest
from psycopg.rows import dict_row

pytestmark = pytest.mark.integration


def _setup_account(client) -> str:
    institution = client.post("/institutions", json={"name": "Queue Bank"}).json()
    checking_id = next(
        t["id"] for t in client.get("/account-types").json() if t["code"] == "checking"
    )
    account = client.post(
        "/accounts",
        json={
            "institution_id": institution["id"],
            "account_type_id": checking_id,
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

_MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj trailer<<>>\n%%EOF\n"
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


def test_pdf_stub_job_ends_in_needs_review(client, db_conn, upload_dir):
    account_id = _setup_account(client)
    response = client.post(
        "/ingest/jobs/pdf",
        data={"account_id": account_id},
        files={"file": ("stmt.pdf", _MINIMAL_PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    body: dict | None = None
    for _ in range(40):
        body = client.get(f"/ingest/jobs/{job_id}").json()
        if body["status"] not in {"pending", "running"}:
            break
    assert body is not None
    assert body["status"] == "needs_review"
    assert body["error_detail"] is not None
    assert "PDF_REVIEW_REQUIRED" in body["error_detail"]
    assert body["parsed_rows"] == 0
    assert body["statement_id"] is not None

    with db_conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, account_id, filename, byte_size, inserted, skipped_duplicates "
            "FROM statements WHERE id = %s",
            (body["statement_id"],),
        )
        stmt = cur.fetchone()
    assert stmt is not None
    assert stmt["account_id"] == uuid.UUID(str(account_id))
    assert stmt["filename"] == "stmt.pdf"
    assert stmt["byte_size"] == len(_MINIMAL_PDF_BYTES)
    assert stmt["inserted"] == 0
    assert stmt["skipped_duplicates"] == 0


def test_pdf_job_rejects_non_pdf(client):
    account_id = _setup_account(client)
    response = client.post(
        "/ingest/jobs/pdf",
        data={"account_id": account_id},
        files={"file": ("not.pdf", b"hello-not-pdf", "application/pdf")},
    )
    assert response.status_code == 422


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
