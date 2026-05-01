"""Rules-first deterministic categorization engine (slice 7)."""

from __future__ import annotations

import psycopg


def apply_rules(conn: psycopg.Connection, transaction_id: str) -> str | None:
    row = conn.execute(
        """
        UPDATE transactions
        SET category_id = (
            SELECT r.category_id
            FROM categorization_rules r
            WHERE transactions.description_normalized ~* r.pattern
            ORDER BY r.priority ASC, r.created_at ASC
            LIMIT 1
        )
        WHERE id = %s
          AND category_id IS NULL
          AND EXISTS (
              SELECT 1 FROM categorization_rules r
              WHERE transactions.description_normalized ~* r.pattern
          )
        RETURNING category_id
        """,
        (transaction_id,),
    ).fetchone()
    return str(row[0]) if row else None


def apply_rules_to_all_uncategorized(conn: psycopg.Connection) -> int:
    result = conn.execute(
        """
        UPDATE transactions
        SET category_id = (
            SELECT r.category_id
            FROM categorization_rules r
            WHERE transactions.description_normalized ~* r.pattern
            ORDER BY r.priority ASC, r.created_at ASC
            LIMIT 1
        )
        WHERE category_id IS NULL
          AND EXISTS (
              SELECT 1 FROM categorization_rules r
              WHERE transactions.description_normalized ~* r.pattern
          )
        """
    )
    return result.rowcount


def apply_rules_retroactively(conn: psycopg.Connection, rule_id: str) -> int:
    rule = conn.execute(
        "SELECT pattern, category_id FROM categorization_rules WHERE id = %s",
        (rule_id,),
    ).fetchone()
    if rule is None:
        return 0
    pattern, category_id = rule
    result = conn.execute(
        """
        UPDATE transactions
        SET category_id = %s
        WHERE category_id IS NULL
          AND description_normalized ~* %s
        """,
        (str(category_id), pattern),
    )
    return result.rowcount
