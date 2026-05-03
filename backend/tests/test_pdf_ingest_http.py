"""PDF ingest HTTP (slice 12) — integration."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

MINIMAL_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj trailer<<>>\n%%EOF\n"


def _pdf_bytes_transaction_lines(lines: list[str]) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in lines:
        pdf.cell(0, 8, text=line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())


def test_ingest_pdf_returns_hitl_when_no_extractable_transactions(client, sample_account_id):
    files = {"file": ("stmt.pdf", MINIMAL_PDF_BYTES, "application/pdf")}
    data = {"account_id": str(sample_account_id)}
    r = client.post("/ingest/pdf", files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] == 0
    assert body["requires_hitl"] is True
    assert body["statement_id"] is None


def test_ingest_pdf_parses_simple_statement_and_persists_transactions(
    client, sample_account_id, db_conn, upload_dir
):
    raw = _pdf_bytes_transaction_lines(
        [
            "03/01/2025  COFFEE SHOP  -4.50",
            "03/02/2025  GROCERY INC  -55.12",
            "2025-03-03  PAYROLL DEP  1200.00",
        ]
    )
    files = {"file": ("stmt.pdf", raw, "application/pdf")}
    data = {"account_id": str(sample_account_id)}
    r = client.post("/ingest/pdf", files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert body["requires_hitl"] is False
    assert body["duplicate_statement"] is False
    assert body["inserted"] == 3
    assert body["skipped_duplicates"] == 0
    assert body["statement_id"] is not None

    sid = body["statement_id"]
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM transactions WHERE source_statement_id = %s",
            (sid,),
        )
        assert cur.fetchone()[0] == 3


def test_ingest_pdf_rejects_non_pdf(client, sample_account_id):
    files = {"file": ("not.pdf", b"hello-not-pdf", "application/pdf")}
    data = {"account_id": str(sample_account_id)}
    r = client.post("/ingest/pdf", files=files, data=data)
    assert r.status_code == 422


def test_ingest_pdf_unknown_account(client):
    files = {"file": ("stmt.pdf", MINIMAL_PDF_BYTES, "application/pdf")}
    data = {"account_id": str(uuid.uuid4())}
    r = client.post("/ingest/pdf", files=files, data=data)
    assert r.status_code == 404


def test_ingest_pdf_over_max_size_returns_413(client, sample_account_id, monkeypatch):
    from pfa import main

    monkeypatch.setattr(main, "MAX_PDF_UPLOAD_BYTES", 32)
    files = {"file": ("stmt.pdf", b"%PDF" + b"x" * 29, "application/pdf")}
    data = {"account_id": str(sample_account_id)}
    r = client.post("/ingest/pdf", files=files, data=data)
    assert r.status_code == 413
