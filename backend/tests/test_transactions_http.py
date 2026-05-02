"""Transaction drill-down HTTP."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration


def test_get_transaction_detail(client, sample_account_id, clean_db):
    aid = str(sample_account_id)
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    with clean_db.cursor() as cur:
        cur.execute(
            "INSERT INTO categories (id, slug, name) VALUES (%s, %s, %s)",
            (str(cid), "groceries", "Groceries"),
        )
        cur.execute(
            """
            INSERT INTO transactions (
              id, account_id, transaction_date, amount, currency,
              description_raw, description_normalized, dedupe_fingerprint, category_id
            ) VALUES (%s, %s, %s, %s, 'USD', 'STORE', 'STORE', %s, %s)
            """,
            (
                str(tid),
                aid,
                datetime.date(2025, 4, 1),
                "-42.50",
                f"fp-{uuid.uuid4()}",
                str(cid),
            ),
        )
    clean_db.commit()

    r = client.get(f"/transactions/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(tid)
    assert body["account_id"] == aid
    assert Decimal(str(body["amount"])) == Decimal("-42.5000")
    assert body["category_slug"] == "groceries"


def test_get_transaction_unknown(client):
    r = client.get(f"/transactions/{uuid.uuid4()}")
    assert r.status_code == 404
