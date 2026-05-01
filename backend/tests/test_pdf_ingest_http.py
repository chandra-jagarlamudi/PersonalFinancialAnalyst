"""PDF ingest HTTP (slice 12) — integration."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

MINIMAL_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj trailer<<>>\n%%EOF\n"


def test_ingest_pdf_stub_returns_hitl_gate(client, sample_account_id):
    files = {"file": ("stmt.pdf", MINIMAL_PDF_BYTES, "application/pdf")}
    data = {"account_id": str(sample_account_id)}
    r = client.post("/ingest/pdf", files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] == 0
    assert body["requires_hitl"] is True
    assert body["confidence"] == "0.35"
    assert "stub_parser" in body["parser_notes"]


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
