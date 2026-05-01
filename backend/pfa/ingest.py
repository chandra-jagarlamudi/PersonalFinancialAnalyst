"""Insert parsed CSV rows with deterministic dedupe."""

from __future__ import annotations

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
    conn: psycopg.Connection, account_id: UUID, rows: list[ParsedCsvRow]
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with conn.cursor() as cur:
        for row in rows:
            desc_norm = normalize_description(row.description_raw)
            fp = transaction_fingerprint(
                account_id,
                row.transaction_date,
                row.posted_date,
                row.amount,
                desc_norm,
            )
            cur.execute(
                """
                INSERT INTO transactions (
                  account_id, transaction_date, posted_date, amount, currency,
                  description_raw, description_normalized, dedupe_fingerprint
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                ),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
    conn.commit()
    return inserted, skipped
