"""HTTP API: CSV ingest, raw file storage, budgets."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pfa.budget_api import router as budget_router
from pfa.recurring_api import router as recurring_router
from pfa.csv_parse import CsvParseError, parse_csv_bytes
from pfa.db import connect, ensure_schema
from pfa.ingest import (
    account_exists,
    advisory_lock_statement_ingest,
    ingest_rows,
    purge_statement,
    record_statement,
    statement_exists_by_hash,
    update_statement_counts,
)
from pfa.storage import delete_file, sha256_hex, store

MAX_CSV_UPLOAD_BYTES = 10 * 1024 * 1024


class IngestResponse(BaseModel):
    inserted: int
    skipped_duplicates: int
    statement_id: str
    duplicate_statement: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.environ.get("DATABASE_URL")
    if url:
        with connect() as conn:
            ensure_schema(conn)
    yield


app = FastAPI(title="Personal Financial Analyst", lifespan=lifespan)

app.include_router(budget_router)
app.include_router(recurring_router)


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

    sha256 = sha256_hex(raw)

    try:
        rows = parse_csv_bytes(raw)
    except CsvParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    with connect() as conn:
        if not account_exists(conn, account_id):
            raise HTTPException(status_code=404, detail="account not found")

        advisory_lock_statement_ingest(conn, account_id, sha256)

        existing = statement_exists_by_hash(conn, account_id, sha256)
        if existing:
            return IngestResponse(
                inserted=existing["inserted"],
                skipped_duplicates=existing["skipped_duplicates"],
                statement_id=existing["id"],
                duplicate_statement=True,
            )

        file_path = store(sha256, raw)

        stmt_id = record_statement(
            conn,
            account_id,
            file.filename or "upload.csv",
            sha256,
            file_path,
            len(raw),
        )
        inserted, skipped = ingest_rows(conn, account_id, rows, source_statement_id=stmt_id)
        update_statement_counts(conn, stmt_id, inserted, skipped)
        conn.commit()

    return IngestResponse(
        inserted=inserted,
        skipped_duplicates=skipped,
        statement_id=str(stmt_id),
    )


@app.delete("/statements/{statement_id}", status_code=204)
def purge_statement_endpoint(statement_id: UUID):
    with connect() as conn:
        file_path = purge_statement(conn, statement_id)
        if file_path is None:
            raise HTTPException(status_code=404, detail="statement not found")
        conn.commit()
    try:
        delete_file(file_path)
    except OSError:
        # DB purge already committed; orphaned bytes are acceptable vs failing the client.
        pass
