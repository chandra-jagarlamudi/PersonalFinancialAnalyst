"""HTTP API (slice 4: CSV ingest)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pfa.csv_parse import CsvParseError, parse_csv_bytes
from pfa.db import connect, ensure_schema
from pfa.ingest import account_exists, ingest_rows

# Upper bound for CSV body size (single read); avoids unbounded memory use per request.
MAX_CSV_UPLOAD_BYTES = 10 * 1024 * 1024


class IngestResponse(BaseModel):
    inserted: int
    skipped_duplicates: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sync schema bootstrap at startup (idempotent DDL).
    url = os.environ.get("DATABASE_URL")
    if url:
        with connect() as conn:
            ensure_schema(conn)
    yield


app = FastAPI(title="Personal Financial Analyst", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest/csv", response_model=IngestResponse)
def ingest_csv(
    account_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
):
    raw = file.file.read(MAX_CSV_UPLOAD_BYTES + 1)
    if len(raw) > MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"CSV exceeds maximum size of {MAX_CSV_UPLOAD_BYTES} bytes",
        )
    try:
        rows = parse_csv_bytes(raw)
    except CsvParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    with connect() as conn:
        if not account_exists(conn, account_id):
            raise HTTPException(status_code=404, detail="account not found")
        inserted, skipped = ingest_rows(conn, account_id, rows)
    return IngestResponse(inserted=inserted, skipped_duplicates=skipped)
