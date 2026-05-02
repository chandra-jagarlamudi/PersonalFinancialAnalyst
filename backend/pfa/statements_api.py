"""HTTP routes for statement listing and detail (Slice 6)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from pfa.db import connect

router = APIRouter(tags=["statements"])


class StatementOut(BaseModel):
    id: UUID
    account_id: UUID
    filename: str
    sha256: str
    byte_size: int
    inserted: int
    skipped_duplicates: int
    created_at: datetime


def _row_to_out(row: dict) -> StatementOut:
    return StatementOut(
        id=row["id"],
        account_id=row["account_id"],
        filename=row["filename"],
        sha256=row["sha256"],
        byte_size=row["byte_size"],
        inserted=row["inserted"],
        skipped_duplicates=row["skipped_duplicates"],
        created_at=row["created_at"],
    )


@router.get("/statements", response_model=list[StatementOut])
def list_statements(account_id: UUID | None = None):
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if account_id is not None:
                cur.execute(
                    """
                    SELECT id, account_id, filename, sha256, byte_size,
                           inserted, skipped_duplicates, created_at
                    FROM statements
                    WHERE account_id = %s
                    ORDER BY created_at DESC
                    """,
                    (str(account_id),),
                )
            else:
                cur.execute(
                    """
                    SELECT id, account_id, filename, sha256, byte_size,
                           inserted, skipped_duplicates, created_at
                    FROM statements
                    ORDER BY created_at DESC
                    """
                )
            return [_row_to_out(row) for row in cur.fetchall()]


@router.get("/statements/{statement_id}", response_model=StatementOut)
def get_statement(statement_id: UUID):
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, account_id, filename, sha256, byte_size,
                       inserted, skipped_duplicates, created_at
                FROM statements
                WHERE id = %s
                """,
                (str(statement_id),),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="statement not found")
    return _row_to_out(row)
