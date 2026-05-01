"""Insert parsed CSV rows with deterministic dedupe; statement record management."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

import psycopg

from pfa.csv_parse import ParsedCsvRow
from pfa.dedupe import normalize_description, transaction_fingerprint


def account_exists(conn: psycopg.Connection, account_id: UUID) -> bool:
    row = conn.execute(
        "SELECT 1 FROM accounts WHERE id = %s LIMIT 1",
        (str(account_id),),
    ).fetchone()
    return row is not None


def ingest_rows(
    conn: psycopg.Connection,
    account_id: UUID,
    rows: list[ParsedCsvRow],
    source_statement_id: UUID | None = None,
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with conn.cursor() as cur:
        for row in rows:
            desc_norm = normalize_description(row.description_raw)
            fp = transaction_fingerprint(
                account_id,
                row.transaction_date,
                row.amount,
                desc_norm,
            )
            cur.execute(
                """
                INSERT INTO transactions (
                  account_id, transaction_date, posted_date, amount, currency,
                  description_raw, description_normalized, dedupe_fingerprint,
                  source_statement_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dedupe_fingerprint) DO NOTHING
                """,
                (
                    str(account_id),
                    row.transaction_date,
                    row.posted_date,
                    row.amount,
                    row.currency,
                    row.description_raw,
                    desc_norm,
                    fp,
                    str(source_statement_id) if source_statement_id else None,
                ),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
    return inserted, skipped


# ---------------------------------------------------------------------------
# Statement record helpers
# ---------------------------------------------------------------------------

def advisory_lock_statement_ingest(
    conn: psycopg.Connection, account_id: UUID, sha256: str
) -> None:
    """Serialize ingest for (account, content hash) so races cannot corrupt counts."""
    payload = f"{account_id}:{sha256}".encode()
    digest = hashlib.sha256(payload).digest()
    k1 = int.from_bytes(digest[0:4], "big", signed=False) & 0x7FFFFFFF
    k2 = int.from_bytes(digest[4:8], "big", signed=False) & 0x7FFFFFFF
    conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (k1, k2))


def statement_exists_by_hash(
    conn: psycopg.Connection, account_id: UUID, sha256: str
) -> dict | None:
    """Return existing statement metadata if this account already ingested this file."""
    row = conn.execute(
        "SELECT id, inserted, skipped_duplicates FROM statements"
        " WHERE account_id = %s AND sha256 = %s",
        (str(account_id), sha256),
    ).fetchone()
    if row is None:
        return None
    return {"id": str(row[0]), "inserted": row[1], "skipped_duplicates": row[2]}


def record_statement(
    conn: psycopg.Connection,
    account_id: UUID,
    filename: str,
    sha256: str,
    file_path: Path,
    byte_size: int,
) -> UUID:
    """Insert statement row (idempotent on concurrent duplicate uploads)."""

    row = conn.execute(
        """
        INSERT INTO statements
          (account_id, filename, sha256, file_path, byte_size)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (account_id, sha256) DO UPDATE SET
          filename = statements.filename
        RETURNING id
        """,
        (str(account_id), filename, sha256, str(file_path), byte_size),
    ).fetchone()
    assert row is not None
    return row[0]


def update_statement_counts(
    conn: psycopg.Connection, statement_id: UUID, inserted: int, skipped: int
) -> None:
    conn.execute(
        "UPDATE statements SET inserted = %s, skipped_duplicates = %s WHERE id = %s",
        (inserted, skipped, str(statement_id)),
    )


def purge_statement(
    conn: psycopg.Connection, statement_id: UUID
) -> str | None:
    """Delete statement record + all transactions sourced from it.

    Returns file_path so caller can remove the file after commit, or None if
    the statement does not exist.
    """
    row = conn.execute(
        "SELECT file_path FROM statements WHERE id = %s",
        (str(statement_id),),
    ).fetchone()
    if row is None:
        return None
    file_path = row[0]
    conn.execute(
        "DELETE FROM transactions WHERE source_statement_id = %s",
        (str(statement_id),),
    )
    conn.execute("DELETE FROM statements WHERE id = %s", (str(statement_id),))
    return file_path
