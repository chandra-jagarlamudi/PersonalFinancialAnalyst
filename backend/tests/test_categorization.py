"""Rules-first categorization + manual correction + rule proposal (integration)."""

from __future__ import annotations

import datetime
import uuid

import pytest

from pfa.categorization import apply_rules
from pfa.db import connect

pytestmark = pytest.mark.integration


def _insert_transaction(clean_db, account_id: uuid.UUID, description: str, amount: str = "-50.00") -> uuid.UUID:
    tx_id = uuid.uuid4()
    with clean_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transactions (
              id, account_id, transaction_date, amount, currency,
              description_raw, description_normalized, dedupe_fingerprint
            ) VALUES (%s, %s, %s, %s, 'USD', %s, %s, %s)
            """,
            (str(tx_id), str(account_id), datetime.date(2025, 1, 15),
             amount, description, description, f"fp-{uuid.uuid4()}"),
        )
    clean_db.commit()
    return tx_id


def _create_category(client, slug: str, name: str) -> str:
    r = client.post("/categories", json={"slug": slug, "name": name})
    assert r.status_code == 200
    return r.json()["id"]


def test_rule_matches_and_categorizes(client, sample_account_id, clean_db):
    cid = _create_category(client, "streaming", "Streaming")
    tx_id = _insert_transaction(clean_db, sample_account_id, "netflix subscription")

    r = client.post(
        "/categorization/rules",
        json={"category_id": cid, "pattern": "netflix", "priority": 100, "apply_retroactively": True},
    )
    assert r.status_code == 201

    with clean_db.cursor() as cur:
        cur.execute("SELECT category_id FROM transactions WHERE id = %s", (str(tx_id),))
        row = cur.fetchone()
    assert str(row[0]) == cid


def test_priority_lower_number_wins(client, sample_account_id, clean_db):
    cid_a = _create_category(client, "cat-a", "Cat A")
    cid_b = _create_category(client, "cat-b", "Cat B")
    tx_id = _insert_transaction(clean_db, sample_account_id, "amazon prime membership")

    client.post("/categorization/rules", json={"category_id": cid_a, "pattern": "amazon", "priority": 50})
    client.post("/categorization/rules", json={"category_id": cid_b, "pattern": "amazon", "priority": 200})

    with connect() as conn:
        matched = apply_rules(conn, str(tx_id))
        conn.commit()

    assert matched == cid_a


def test_no_matching_rule_leaves_uncategorized(client, sample_account_id, clean_db):
    cid = _create_category(client, "streaming2", "Streaming 2")
    tx_id = _insert_transaction(clean_db, sample_account_id, "random merchant xyz")
    client.post("/categorization/rules", json={"category_id": cid, "pattern": "netflix"})

    with connect() as conn:
        matched = apply_rules(conn, str(tx_id))
        conn.commit()

    assert matched is None

    with clean_db.cursor() as cur:
        cur.execute("SELECT category_id FROM transactions WHERE id = %s", (str(tx_id),))
        row = cur.fetchone()
    assert row[0] is None


def test_invalid_regex_returns_422(client):
    cid = _create_category(client, "misc", "Misc")
    r = client.post("/categorization/rules", json={"category_id": cid, "pattern": "[invalid("})
    assert r.status_code == 422


def test_manual_category_correction(client, sample_account_id, clean_db):
    cid = _create_category(client, "groceries", "Groceries")
    tx_id = _insert_transaction(clean_db, sample_account_id, "whole foods market")

    r = client.put(f"/transactions/{tx_id}/category", json={"category_id": cid})
    assert r.status_code == 200
    assert r.json()["category_id"] == cid


def test_manual_correction_unknown_transaction_404(client):
    cid = _create_category(client, "transport", "Transport")
    r = client.put(f"/transactions/{uuid.uuid4()}/category", json={"category_id": cid})
    assert r.status_code == 404


def test_rule_proposal_dry_run_does_not_persist(client, sample_account_id, clean_db):
    cid = _create_category(client, "rides", "Rides")
    tx_id1 = _insert_transaction(clean_db, sample_account_id, "uber trip")
    tx_id2 = _insert_transaction(clean_db, sample_account_id, "uber eats order")

    r = client.post(
        f"/transactions/{tx_id1}/rule-proposal",
        json={"pattern": "uber", "apply_retroactively": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["proposed_rule"]["pattern"] == "uber"
    assert body["would_affect_count"] == 2

    # Dry-run must not create a rule
    rules = client.get("/categorization/rules").json()
    assert rules == []

    # Transactions must remain uncategorized
    with clean_db.cursor() as cur:
        cur.execute("SELECT category_id FROM transactions WHERE id = ANY(%s)", ([str(tx_id1), str(tx_id2)],))
        rows = cur.fetchall()
    assert all(r[0] is None for r in rows)
