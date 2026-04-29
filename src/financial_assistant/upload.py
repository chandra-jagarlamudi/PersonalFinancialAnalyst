"""POST /upload endpoint for bank statement ingestion.

T-045: Upload endpoint — multipart, optional bank field, 400/409 validation
T-052: Hash + atomic write via insert_statement_and_transactions
T-054: LangSmith ingestion pipeline tracing
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from financial_assistant.db import get_session
from financial_assistant.models import Statement
from financial_assistant.normalization import NormalizedRow, normalize_transactions
from financial_assistant.parsers import (
    detect_bank,
    parse_amex,
    parse_capital_one,
    parse_chase,
    parse_robinhood,
)
from financial_assistant.queries import insert_statement_and_transactions
from financial_assistant.tracing import trace_span

log = structlog.get_logger()

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/csv",
    "text/plain",
    "application/vnd.ms-excel",
    "application/octet-stream",
}

_ALLOWED_EXTENSIONS = {".pdf", ".csv"}


@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    bank: Optional[str] = Form(default=None),
) -> JSONResponse:
    """T-045: Ingest a bank statement PDF or CSV."""
    filename = file.filename or "upload"

    # T-045: Validate file type by extension + content-type
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    is_pdf = ext == ".pdf" or content_type == "application/pdf"
    is_csv = ext == ".csv" or content_type in ("text/csv", "text/plain")

    if not is_pdf and not is_csv:
        raise HTTPException(status_code=400, detail="Only PDF and CSV files are accepted")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    with trace_span("ingestion", inputs={"filename": filename, "bank_hint": bank}):
        # T-046: Auto-detect bank if not provided
        with trace_span("detect_bank"):
            bank_detected = bank or detect_bank(filename, content)
            if not bank_detected:
                raise HTTPException(
                    status_code=400,
                    detail="Could not detect bank. Provide 'bank' field (chase/amex/capital_one/robinhood)",
                )

        # T-047–T-050: Parse raw rows
        with trace_span("parse", inputs={"bank": bank_detected}):
            raw_rows = _parse(bank_detected, content, is_pdf)

        if not raw_rows:
            raise HTTPException(
                status_code=422,
                detail=f"No transactions found in file for bank={bank_detected}",
            )

        # T-051: Normalize + intra-upload dedup
        with trace_span("normalize"):
            normalized = normalize_transactions(raw_rows)

        # T-052: Compute file hash + atomic write
        with trace_span("db_write"):
            file_hash = hashlib.sha256(content).hexdigest()

            dates = [r.date for r in normalized]
            period_start = min(dates) if dates else None
            period_end = max(dates) if dates else None

            statement = Statement(
                id=uuid.uuid4(),
                filename=filename,
                source_bank=bank_detected,
                file_hash=file_hash,
                period_start=period_start,
                period_end=period_end,
                transaction_count=len(normalized),
                status="processing",
            )

            import datetime as _dt
            statement.ingested_at = _dt.datetime.now(_dt.timezone.utc)
            statement.status = "ingested"

            tx_dicts = _rows_to_dicts(normalized, bank_detected)

            async with get_session() as db:
                result = await insert_statement_and_transactions(db, statement, tx_dicts)

            if result is None:
                # T-052: Duplicate file detected
                log.info("upload.duplicate", file_hash=file_hash[:16], filename=filename)
                raise HTTPException(status_code=409, detail="File already ingested")

            attempted, inserted = result
            duplicates_skipped = attempted - inserted

    log.info(
        "upload.success",
        filename=filename,
        bank=bank_detected,
        transaction_count=inserted,
        duplicates_skipped=duplicates_skipped,
    )

    return JSONResponse(
        {
            "statement_id": str(statement.id),
            "bank_detected": bank_detected,
            "transaction_count": inserted,
            "duplicates_skipped": duplicates_skipped,
            "period_start": str(period_start) if period_start else None,
            "period_end": str(period_end) if period_end else None,
        }
    )


def _parse(bank: str, content: bytes, is_pdf: bool) -> list:
    """Dispatch to the correct parser."""
    b = bank.lower()
    if b == "chase":
        return parse_chase(content)
    if b == "amex":
        return parse_amex(content, is_pdf=is_pdf)
    if b == "capital_one":
        return parse_capital_one(content)
    if b == "robinhood":
        return parse_robinhood(content)
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported bank: {bank!r}. Use chase/amex/capital_one/robinhood",
    )


def _rows_to_dicts(rows: list[NormalizedRow], source_bank: str) -> list[dict]:
    """Convert normalized rows to dicts suitable for insert_transactions."""
    import datetime as _dt

    return [
        {
            "id": uuid.uuid4(),
            "source_bank": source_bank,
            "date": r.date,
            "description": r.description,
            "merchant": r.merchant,
            "amount": r.amount,
            "currency": "USD",
            "transaction_type": r.transaction_type,
            "category": r.category,
            "raw_description_hash": r.raw_description_hash,
            "created_at": _dt.datetime.now(_dt.timezone.utc),
        }
        for r in rows
    ]
