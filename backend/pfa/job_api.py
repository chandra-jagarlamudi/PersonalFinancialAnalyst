"""Ingest job HTTP routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from pfa.ingest_jobs import (
    create_csv_job,
    create_pdf_job,
    dispatch_ingest_job_sync,
    get_job,
    list_jobs,
    retry_job,
)

router = APIRouter(prefix="/ingest/jobs", tags=["ingest-jobs"])


class JobStepOut(BaseModel):
    step_key: str
    status: str
    item_count: int | None = None
    detail: str | None = None


class JobOut(BaseModel):
    id: UUID
    job_type: str
    status: str
    account_id: UUID
    statement_id: UUID | None = None
    filename: str
    byte_size: int
    parsed_rows: int | None = None
    inserted_rows: int | None = None
    skipped_duplicates: int | None = None
    error_detail: str | None = None
    retry_count: int
    steps: list[JobStepOut] = []


def _row_to_job_out(row: dict) -> JobOut:
    return JobOut(
        id=row["id"],
        job_type=row["job_type"],
        status=row["status"],
        account_id=row["account_id"],
        statement_id=row.get("statement_id"),
        filename=row["filename"],
        byte_size=row["byte_size"],
        parsed_rows=row["parsed_rows"],
        inserted_rows=row["inserted_rows"],
        skipped_duplicates=row["skipped_duplicates"],
        error_detail=row["error_detail"],
        retry_count=row["retry_count"],
        steps=[JobStepOut(**step) for step in row.get("steps", [])],
    )


@router.get("", response_model=list[JobOut])
def get_jobs(limit: int = Query(default=20, ge=1, le=100)):
    return [_row_to_job_out(row) for row in list_jobs(limit=limit)]


@router.get("/{job_id}", response_model=JobOut)
def get_job_by_id(job_id: UUID):
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _row_to_job_out(row)


@router.post("/csv", response_model=JobOut, status_code=202)
def post_csv_job(
    background_tasks: BackgroundTasks,
    account_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
):
    raw = file.file.read()
    try:
        job_id = create_csv_job(account_id, file.filename or "upload.csv", raw)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(dispatch_ingest_job_sync, job_id)
    row = get_job(job_id)
    assert row is not None
    return _row_to_job_out(row)


@router.post("/pdf", response_model=JobOut, status_code=202)
def post_pdf_job(
    background_tasks: BackgroundTasks,
    account_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
):
    raw = file.file.read()
    try:
        job_id = create_pdf_job(account_id, file.filename or "upload.pdf", raw)
    except ValueError as exc:
        detail = str(exc)
        if detail == "account not found":
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc
    background_tasks.add_task(dispatch_ingest_job_sync, job_id)
    row = get_job(job_id)
    assert row is not None
    return _row_to_job_out(row)


@router.post("/{job_id}/retry", response_model=JobOut)
def post_retry_job(job_id: UUID, background_tasks: BackgroundTasks):
    try:
        retry_job(job_id)
    except ValueError as exc:
        message = str(exc)
        if message == "job not found":
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=409, detail=message) from exc
    background_tasks.add_task(dispatch_ingest_job_sync, job_id)
    row = get_job(job_id)
    assert row is not None
    return _row_to_job_out(row)
