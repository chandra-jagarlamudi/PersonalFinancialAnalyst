"""Durable CSV ingest job tracking and ledger persistence."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from psycopg.rows import dict_row

from pfa.csv_parse import CsvParseError, parse_csv_bytes
from pfa.db import connect
from pfa.dedupe import normalize_description, transaction_fingerprint
from pfa.ingest import (
    account_exists,
    advisory_lock_statement_ingest,
    ingest_rows,
    record_statement,
    statement_exists_by_hash,
    update_statement_counts,
)
from pfa.pdf_cc import outcome_requires_hitl, parse_targeted_credit_card_pdf_stub
from pfa.storage import sha256_hex, store

JOB_TYPE_CSV = "csv-import"
JOB_TYPE_PDF = "pdf-import"
STEP_KEYS = ("extract", "normalize", "dedupe", "categorize", "persist")
ACTIVE_STATUSES = {"pending", "running"}


def create_csv_job(account_id: UUID, filename: str, raw: bytes) -> UUID:
    sha256 = sha256_hex(raw)
    with connect() as conn:
        if not account_exists(conn, account_id):
            raise ValueError("account not found")
        file_path = store(sha256, raw)
        row = conn.execute(
            """
            INSERT INTO ingest_jobs (
              job_type, status, account_id, filename, file_path, sha256, byte_size
            ) VALUES (%s, 'pending', %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (JOB_TYPE_CSV, str(account_id), filename, str(file_path), sha256, len(raw)),
        ).fetchone()
        assert row is not None
        job_id = row[0]
        with conn.cursor() as cur:
            for step_key in STEP_KEYS:
                cur.execute(
                    """
                    INSERT INTO ingest_job_steps (job_id, step_key, status)
                    VALUES (%s, %s, 'pending')
                    """,
                    (str(job_id), step_key),
                )
        conn.commit()
    return job_id


def create_pdf_job(account_id: UUID, filename: str, raw: bytes) -> UUID:
    if len(raw) < 5 or not raw.startswith(b"%PDF"):
        raise ValueError("upload must be a PDF (%PDF header)")
    sha256 = sha256_hex(raw)
    with connect() as conn:
        if not account_exists(conn, account_id):
            raise ValueError("account not found")
        file_path = store(sha256, raw)
        row = conn.execute(
            """
            INSERT INTO ingest_jobs (
              job_type, status, account_id, filename, file_path, sha256, byte_size
            ) VALUES (%s, 'pending', %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (JOB_TYPE_PDF, str(account_id), filename, str(file_path), sha256, len(raw)),
        ).fetchone()
        assert row is not None
        job_id = row[0]
        with conn.cursor() as cur:
            for step_key in STEP_KEYS:
                cur.execute(
                    """
                    INSERT INTO ingest_job_steps (job_id, step_key, status)
                    VALUES (%s, %s, 'pending')
                    """,
                    (str(job_id), step_key),
                )
        conn.commit()
    return job_id


def _update_job_status(
    conn,
    job_id: UUID,
    *,
    status: str,
    error_detail: str | None = None,
    parsed_rows: int | None = None,
    inserted_rows: int | None = None,
    skipped_duplicates: int | None = None,
    statement_id: UUID | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
    increment_retry: bool = False,
) -> None:
    conn.execute(
        """
        UPDATE ingest_jobs
        SET status = %s,
            error_detail = %s,
            parsed_rows = COALESCE(%s, parsed_rows),
            inserted_rows = COALESCE(%s, inserted_rows),
            skipped_duplicates = COALESCE(%s, skipped_duplicates),
            statement_id = COALESCE(%s, statement_id),
            started_at = CASE WHEN %s THEN COALESCE(started_at, now()) ELSE started_at END,
            finished_at = CASE WHEN %s THEN now() ELSE finished_at END,
            retry_count = CASE WHEN %s THEN retry_count + 1 ELSE retry_count END,
            updated_at = now()
        WHERE id = %s
        """,
        (
            status,
            error_detail,
            parsed_rows,
            inserted_rows,
            skipped_duplicates,
            str(statement_id) if statement_id else None,
            mark_started,
            mark_finished,
            increment_retry,
            str(job_id),
        ),
    )


def _mark_step(
    conn,
    job_id: UUID,
    step_key: str,
    *,
    status: str,
    item_count: int | None = None,
    detail: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ingest_job_steps
        SET status = %s,
            item_count = %s,
            detail = %s,
            started_at = CASE WHEN %s = 'running' THEN now() ELSE COALESCE(started_at, now()) END,
            finished_at = CASE WHEN %s IN ('completed', 'failed') THEN now() ELSE finished_at END
        WHERE job_id = %s AND step_key = %s
        """,
        (status, item_count, detail, status, status, str(job_id), step_key),
    )


def _count_in_file_duplicates(account_id: UUID, rows) -> int:
    seen: set[str] = set()
    duplicate_count = 0
    for row in rows:
        fingerprint = transaction_fingerprint(
            account_id,
            row.transaction_date,
            row.amount,
            normalize_description(row.description_raw),
        )
        if fingerprint in seen:
            duplicate_count += 1
        else:
            seen.add(fingerprint)
    return duplicate_count


def process_csv_job(job_id: UUID) -> None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT account_id, file_path, filename, sha256, byte_size
            FROM ingest_jobs
            WHERE id = %s
            LIMIT 1
            """,
            (str(job_id),),
        ).fetchone()
        if row is None:
            return
        account_id = UUID(str(row[0]))
        file_path = Path(row[1])
        filename = row[2]
        sha256 = row[3]
        byte_size = row[4]
        _update_job_status(conn, job_id, status="running", mark_started=True)
        _mark_step(conn, job_id, "extract", status="running")
        conn.commit()

    try:
        raw = file_path.read_bytes()
        with connect() as conn:
            _mark_step(conn, job_id, "extract", status="completed", item_count=len(raw))
            _mark_step(conn, job_id, "normalize", status="running")
            conn.commit()

        rows = parse_csv_bytes(raw)
        duplicate_count = _count_in_file_duplicates(account_id, rows)

        with connect() as conn:
            _mark_step(conn, job_id, "normalize", status="completed", item_count=len(rows))
            _mark_step(conn, job_id, "dedupe", status="running")
            conn.commit()

        with connect() as conn:
            _mark_step(conn, job_id, "dedupe", status="completed", item_count=duplicate_count)
            _mark_step(conn, job_id, "persist", status="running")
            advisory_lock_statement_ingest(conn, account_id, sha256)
            existing = statement_exists_by_hash(conn, account_id, sha256)
            if existing is not None:
                _mark_step(
                    conn,
                    job_id,
                    "categorize",
                    status="completed",
                    item_count=existing["inserted"],
                    detail="reused categorization from the existing statement import",
                )
                _mark_step(
                    conn,
                    job_id,
                    "persist",
                    status="completed",
                    item_count=existing["inserted"],
                    detail="statement already ingested; reused existing ledger rows",
                )
                _update_job_status(
                    conn,
                    job_id,
                    status="succeeded",
                    parsed_rows=len(rows),
                    inserted_rows=existing["inserted"],
                    skipped_duplicates=existing["skipped_duplicates"],
                    statement_id=UUID(existing["id"]),
                    mark_finished=True,
                )
                conn.commit()
                return

            statement_id = record_statement(
                conn,
                account_id,
                filename,
                sha256,
                file_path,
                byte_size,
            )
            inserted, skipped = ingest_rows(
                conn,
                account_id,
                rows,
                source_statement_id=statement_id,
            )
            update_statement_counts(conn, statement_id, inserted, skipped)
            _mark_step(
                conn,
                job_id,
                "categorize",
                status="completed",
                item_count=inserted,
                detail="applied category rules while inserting transactions",
            )
            _mark_step(
                conn,
                job_id,
                "persist",
                status="completed",
                item_count=inserted,
                detail="statement and transactions persisted to the ledger",
            )
            _update_job_status(
                conn,
                job_id,
                status="succeeded",
                parsed_rows=len(rows),
                inserted_rows=inserted,
                skipped_duplicates=skipped,
                statement_id=statement_id,
                mark_finished=True,
            )
            conn.commit()
    except CsvParseError as exc:
        with connect() as conn:
            _mark_step(conn, job_id, "normalize", status="failed", detail=str(exc))
            _update_job_status(
                conn,
                job_id,
                status="failed",
                error_detail=str(exc),
                mark_finished=True,
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        with connect() as conn:
            _mark_step(conn, job_id, "persist", status="failed", detail=str(exc))
            _update_job_status(
                conn,
                job_id,
                status="failed",
                error_detail=str(exc),
                mark_finished=True,
            )
            conn.commit()


def process_pdf_job(job_id: UUID) -> None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT account_id, file_path, filename, sha256, byte_size
            FROM ingest_jobs
            WHERE id = %s
            LIMIT 1
            """,
            (str(job_id),),
        ).fetchone()
        if row is None:
            return
        account_id = UUID(str(row[0]))
        file_path = Path(row[1])
        filename = row[2]
        sha256 = row[3]
        byte_size = row[4]
        _update_job_status(conn, job_id, status="running", mark_started=True)
        _mark_step(conn, job_id, "extract", status="running")
        conn.commit()

    try:
        raw = file_path.read_bytes()
        with connect() as conn:
            _mark_step(conn, job_id, "extract", status="completed", item_count=len(raw))
            _mark_step(conn, job_id, "normalize", status="running")
            conn.commit()

        outcome = parse_targeted_credit_card_pdf_stub(raw)
        rows = list(outcome.rows)

        if outcome_requires_hitl(outcome):
            with connect() as conn:
                _mark_step(
                    conn,
                    job_id,
                    "normalize",
                    status="completed",
                    item_count=len(rows),
                    detail=outcome.notes,
                )
                for step_key in ("dedupe", "categorize", "persist"):
                    _mark_step(
                        conn,
                        job_id,
                        step_key,
                        status="skipped",
                        detail="blocked until PDF parse is reviewed or parser confidence improves",
                    )
                _update_job_status(
                    conn,
                    job_id,
                    status="needs_review",
                    error_detail=(
                        f"PDF_REVIEW_REQUIRED confidence={outcome.confidence} "
                        f"rows={len(rows)} notes={outcome.notes}"
                    ),
                    parsed_rows=len(rows),
                    mark_finished=True,
                )
                conn.commit()
            return

        duplicate_count = _count_in_file_duplicates(account_id, rows)

        with connect() as conn:
            _mark_step(conn, job_id, "normalize", status="completed", item_count=len(rows))
            _mark_step(conn, job_id, "dedupe", status="running")
            conn.commit()

        with connect() as conn:
            _mark_step(conn, job_id, "dedupe", status="completed", item_count=duplicate_count)
            _mark_step(conn, job_id, "persist", status="running")
            advisory_lock_statement_ingest(conn, account_id, sha256)
            existing = statement_exists_by_hash(conn, account_id, sha256)
            if existing is not None:
                _mark_step(
                    conn,
                    job_id,
                    "categorize",
                    status="completed",
                    item_count=existing["inserted"],
                    detail="reused categorization from the existing statement import",
                )
                _mark_step(
                    conn,
                    job_id,
                    "persist",
                    status="completed",
                    item_count=existing["inserted"],
                    detail="statement already ingested; reused existing ledger rows",
                )
                _update_job_status(
                    conn,
                    job_id,
                    status="succeeded",
                    parsed_rows=len(rows),
                    inserted_rows=existing["inserted"],
                    skipped_duplicates=existing["skipped_duplicates"],
                    statement_id=UUID(existing["id"]),
                    mark_finished=True,
                )
                conn.commit()
                return

            statement_id = record_statement(
                conn,
                account_id,
                filename,
                sha256,
                file_path,
                byte_size,
            )
            inserted, skipped = ingest_rows(
                conn,
                account_id,
                rows,
                source_statement_id=statement_id,
            )
            update_statement_counts(conn, statement_id, inserted, skipped)
            _mark_step(
                conn,
                job_id,
                "categorize",
                status="completed",
                item_count=inserted,
                detail="applied category rules while inserting transactions",
            )
            _mark_step(
                conn,
                job_id,
                "persist",
                status="completed",
                item_count=inserted,
                detail="statement and transactions persisted to the ledger",
            )
            _update_job_status(
                conn,
                job_id,
                status="succeeded",
                parsed_rows=len(rows),
                inserted_rows=inserted,
                skipped_duplicates=skipped,
                statement_id=statement_id,
                mark_finished=True,
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        with connect() as conn:
            _mark_step(conn, job_id, "persist", status="failed", detail=str(exc))
            _update_job_status(
                conn,
                job_id,
                status="failed",
                error_detail=str(exc),
                mark_finished=True,
            )
            conn.commit()


def dispatch_ingest_job_sync(job_id: UUID) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT job_type FROM ingest_jobs WHERE id = %s LIMIT 1",
            (str(job_id),),
        ).fetchone()
    if row is None:
        return
    job_type = row[0]
    if job_type == JOB_TYPE_CSV:
        process_csv_job(job_id)
    elif job_type == JOB_TYPE_PDF:
        process_pdf_job(job_id)
    else:
        with connect() as conn:
            _update_job_status(
                conn,
                job_id,
                status="failed",
                error_detail=f"unknown job_type {job_type!r}",
                mark_finished=True,
            )
            conn.commit()


def list_jobs(limit: int = 20) -> list[dict]:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, job_type, status, account_id, statement_id, filename, byte_size,
                       parsed_rows, inserted_rows, skipped_duplicates, error_detail,
                       retry_count, created_at, updated_at, started_at, finished_at
                FROM ingest_jobs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def get_job(job_id: UUID) -> dict | None:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, job_type, status, account_id, statement_id, filename, file_path, sha256,
                       byte_size, parsed_rows, inserted_rows, skipped_duplicates,
                       error_detail, retry_count, created_at, updated_at, started_at, finished_at
                FROM ingest_jobs
                WHERE id = %s
                LIMIT 1
                """,
                (str(job_id),),
            )
            job = cur.fetchone()
            if job is None:
                return None
            cur.execute(
                """
                SELECT step_key, status, item_count, detail, started_at, finished_at
                FROM ingest_job_steps
                WHERE job_id = %s
                ORDER BY CASE step_key
                  WHEN 'extract' THEN 1
                  WHEN 'normalize' THEN 2
                  WHEN 'dedupe' THEN 3
                  WHEN 'categorize' THEN 4
                  WHEN 'persist' THEN 5
                  ELSE 99
                END
                """,
                (str(job_id),),
            )
            steps = [dict(step) for step in cur.fetchall()]
            out = dict(job)
            out["steps"] = steps
            return out


def retry_job(job_id: UUID) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM ingest_jobs WHERE id = %s LIMIT 1",
            (str(job_id),),
        ).fetchone()
        if row is None:
            raise ValueError("job not found")
        if row[0] != "failed":
            raise ValueError("job is not retryable")
        conn.execute(
            """
            UPDATE ingest_jobs
            SET status = 'pending',
                error_detail = NULL,
                started_at = NULL,
                finished_at = NULL,
                updated_at = now(),
                parsed_rows = NULL,
                inserted_rows = NULL,
                skipped_duplicates = NULL,
                retry_count = retry_count + 1,
                statement_id = NULL
            WHERE id = %s
            """,
            (str(job_id),),
        )
        with conn.cursor() as cur:
            for step_key in STEP_KEYS:
                cur.execute(
                    """
                    UPDATE ingest_job_steps
                    SET status = 'pending',
                        item_count = NULL,
                        detail = NULL,
                        started_at = NULL,
                        finished_at = NULL
                    WHERE job_id = %s AND step_key = %s
                    """,
                    (str(job_id), step_key),
                )
        conn.commit()


def recoverable_job_ids() -> list[UUID]:
    statuses = tuple(ACTIVE_STATUSES)
    with connect() as conn:
        rows = conn.execute(
            "SELECT id FROM ingest_jobs WHERE status = ANY(%s)",
            (list(statuses),),
        ).fetchall()
    return [UUID(str(row[0])) for row in rows]
