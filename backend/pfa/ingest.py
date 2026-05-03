"""Insert parsed CSV rows with deterministic dedupe; statement record management."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg

from pfa.budget_service import list_categories
from pfa.categorization import apply_rules, category_id_from_rules
from pfa.llm_category_suggest import suggest_category_slug
from pfa.csv_parse import ParsedCsvRow
from pfa.dedupe import normalize_description, transaction_fingerprint

# Matches transactions.amount NUMERIC(18, 4) and transaction_fingerprint amount token.
_LEDGER_AMOUNT_QUANT = Decimal("0.0001")


def normalize_parsed_row_for_db(row: ParsedCsvRow) -> ParsedCsvRow:
    """Coerce parsed fields to canonical shapes before INSERT (DATE stays calendar date)."""
    cur = (row.currency or "").strip().upper() or "USD"
    amt = row.amount.quantize(_LEDGER_AMOUNT_QUANT)
    desc = row.description_raw.strip()
    return ParsedCsvRow(
        transaction_date=row.transaction_date,
        posted_date=row.posted_date,
        amount=amt,
        currency=cur,
        description_raw=desc,
    )


def resolve_initial_category_id(
    conn: psycopg.Connection,
    *,
    description_raw: str,
    description_normalized: str,
    llm_if_unmatched: bool,
) -> str | None:
    rid = category_id_from_rules(conn, description_normalized)
    if rid is not None:
        return rid
    if not llm_if_unmatched:
        return None
    cats = list_categories(conn)
    slug, err = suggest_category_slug(
        description_raw=description_raw,
        description_normalized=description_normalized,
        categories=cats,
    )
    if err or not slug:
        return None
    for c in cats:
        if c["slug"] == slug:
            return str(c["id"])
    return None


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
    *,
    llm_if_unmatched: bool = False,
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with conn.cursor() as cur:
        for row in rows:
            row = normalize_parsed_row_for_db(row)
            desc_norm = normalize_description(row.description_raw)
            cat_id = resolve_initial_category_id(
                conn,
                description_raw=row.description_raw,
                description_normalized=desc_norm,
                llm_if_unmatched=llm_if_unmatched,
            )
            fp = transaction_fingerprint(
                account_id,
                row.transaction_date,
                row.amount,
                desc_norm,
            )
            result = cur.execute(
                """
                INSERT INTO transactions (
                  account_id, transaction_date, posted_date, amount, currency,
                  description_raw, description_normalized, dedupe_fingerprint,
                  source_statement_id, category_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dedupe_fingerprint) DO NOTHING
                RETURNING id
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
                    cat_id,
                ),
            ).fetchone()
            if result is not None:
                inserted += 1
                apply_rules(conn, str(result[0]))
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
