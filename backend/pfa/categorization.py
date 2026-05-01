"""Rules-first deterministic categorization engine (slice 7)."""

from __future__ import annotations

import re

import psycopg


def apply_rules(conn: psycopg.Connection, transaction_id: str) -> str | None:
    tx = conn.execute(
        "SELECT description_normalized FROM transactions WHERE id = %s AND category_id IS NULL",
        (transaction_id,),
    ).fetchone()
    if tx is None:
        return None
    desc = tx[0]
    rules = conn.execute(
        "SELECT category_id, pattern FROM categorization_rules ORDER BY priority ASC, created_at ASC"
    ).fetchall()
    for category_id, pattern in rules:
        try:
            if re.search(pattern, desc, re.IGNORECASE):
                conn.execute(
                    "UPDATE transactions SET category_id = %s WHERE id = %s",
                    (str(category_id), transaction_id),
                )
                return str(category_id)
        except re.error:
            continue
    return None


def apply_rules_to_all_uncategorized(conn: psycopg.Connection) -> int:
    rules = conn.execute(
        "SELECT category_id, pattern FROM categorization_rules ORDER BY priority ASC, created_at ASC"
    ).fetchall()
    if not rules:
        return 0
    txs = conn.execute(
        "SELECT id, description_normalized FROM transactions WHERE category_id IS NULL"
    ).fetchall()
    updated = 0
    with conn.cursor() as cur:
        for tx_id, desc in txs:
            for category_id, pattern in rules:
                try:
                    if re.search(pattern, desc, re.IGNORECASE):
                        cur.execute(
                            "UPDATE transactions SET category_id = %s WHERE id = %s",
                            (str(category_id), str(tx_id)),
                        )
                        updated += 1
                        break
                except re.error:
                    continue
    return updated


def apply_rules_retroactively(conn: psycopg.Connection, rule_id: str) -> int:
    rule = conn.execute(
        "SELECT pattern, category_id FROM categorization_rules WHERE id = %s",
        (rule_id,),
    ).fetchone()
    if rule is None:
        return 0
    pattern, category_id = rule
    txs = conn.execute(
        "SELECT id, description_normalized FROM transactions WHERE category_id IS NULL"
    ).fetchall()
    updated = 0
    with conn.cursor() as cur:
        for tx_id, desc in txs:
            try:
                if re.search(pattern, desc, re.IGNORECASE):
                    cur.execute(
                        "UPDATE transactions SET category_id = %s WHERE id = %s",
                        (str(category_id), str(tx_id)),
                    )
                    updated += 1
            except re.error:
                break
    return updated
