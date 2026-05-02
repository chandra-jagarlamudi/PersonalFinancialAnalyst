"""Envelope budget HTTP API (integration)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

pytestmark = pytest.mark.integration


def _insert_expense(
    clean_db, account_id: uuid.UUID, category_id: uuid.UUID, d: date, amount: str
) -> None:
    fp = f"test-{uuid.uuid4()}"
    with clean_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transactions (
              account_id, transaction_date, amount, currency,
              description_raw, description_normalized, dedupe_fingerprint, category_id
            ) VALUES (%s, %s, %s, 'USD', 'test', 'test', %s, %s)
            """,
            (str(account_id), d, amount, fp, str(category_id)),
        )
    clean_db.commit()


def test_categories_crud_list(client):
    assert client.get("/categories").json() == []
    r = client.post("/categories", json={"slug": "groceries", "name": "Groceries"})
    assert r.status_code == 200
    row = r.json()
    assert row["slug"] == "groceries"
    listed = client.get("/categories").json()
    assert len(listed) == 1
    assert listed[0]["id"] == row["id"]


def test_duplicate_category_slug_conflict(client):
    assert client.post("/categories", json={"slug": "dup", "name": "One"}).status_code == 200
    assert client.post("/categories", json={"slug": "dup", "name": "Two"}).status_code == 409


def test_budget_put_get_and_status_projection(client, sample_account_id, clean_db):
    cat = client.post("/categories", json={"slug": "food", "name": "Food"})
    cid = cat.json()["id"]
    assert (
        client.put(
            "/budgets/2025-03",
            json={"items": [{"category_id": cid, "amount": "500"}]},
        ).status_code
        == 204
    )
    rows = client.get("/budgets/2025-03").json()
    assert len(rows) == 1
    assert rows[0]["amount"] == "500.0000"

    _insert_expense(clean_db, sample_account_id, uuid.UUID(cid), date(2025, 3, 5), "-120")

    st = client.get("/budgets/2025-03/status", params={"as_of": "2025-03-10"}).json()
    assert len(st) == 1
    row = st[0]
    assert row["spent_mtd"] == "120.0000"
    assert row["projected_spend"] == "372.0000"
    assert row["budget_amount"] == "500.0000"
    assert row["remaining_mtd"] == "380.0000"
    assert row["days_elapsed"] == 10
    assert row["days_in_month"] == 31


def test_budget_put_unknown_category_returns_404(client):
    missing = str(uuid.uuid4())
    r = client.put(
        "/budgets/2025-04",
        json={"items": [{"category_id": missing, "amount": "100"}]},
    )
    assert r.status_code == 404


def test_suggest_averages_total_over_lookback_months(client, sample_account_id, clean_db):
    cat = client.post("/categories", json={"slug": "fun", "name": "Fun"})
    cid = uuid.UUID(cat.json()["id"])
    _insert_expense(clean_db, sample_account_id, cid, date(2025, 1, 10), "-100")
    _insert_expense(clean_db, sample_account_id, cid, date(2025, 2, 11), "-200")
    sug = client.post(
        "/budgets/2025-03/suggest",
        json={"lookback_months": 2},
    ).json()
    assert len(sug) == 1
    assert sug[0]["suggested_amount"] == "150.0000"
    assert sug[0]["history_total_spend"] == "300.0000"


def test_budget_status_empty(client):
    assert client.get("/budgets/2025-01/status").json() == []


def test_budget_suggest_empty(client):
    assert client.post("/budgets/2025-01/suggest", json={}).json() == []


def test_invalid_year_month_returns_422(client):
    assert client.get("/budgets/2025-13/status").status_code == 422
    assert client.get("/budgets/not-a-date/status").status_code == 422
