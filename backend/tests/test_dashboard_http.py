"""Dashboard and transaction explorer API tests."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _create_setup(client):
    institution = client.post("/institutions", json={"name": "Demo Bank"}).json()
    category = client.post("/categories", json={"slug": "groceries", "name": "Groceries"}).json()
    account = client.post(
        "/accounts",
        json={
            "institution_id": institution["id"],
            "name": "Checking",
            "currency": "USD",
        },
    ).json()
    return account, category


def test_manual_transactions_drive_dashboard_and_explorer(client):
    account, category = _create_setup(client)

    first = client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "transaction_date": "2025-04-05",
            "amount": "-42.50",
            "currency": "USD",
            "description": "Whole Foods",
            "category_id": category["id"],
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "transaction_date": "2025-04-10",
            "amount": "1500.00",
            "currency": "USD",
            "description": "Salary",
        },
    )
    assert second.status_code == 200

    listed = client.get("/transactions", params={"q": "Whole", "limit": 10})
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["description_raw"] == "Whole Foods"
    assert rows[0]["category_name"] == "Groceries"

    cashflow = client.get("/dashboard/cashflow", params={"months": 24})
    assert cashflow.status_code == 200
    cashflow_rows = cashflow.json()
    assert any(row["income_total"] == "1500.0000" for row in cashflow_rows)
    assert any(row["expense_total_abs"] == "42.5000" for row in cashflow_rows)

    category_spend = client.get("/dashboard/category-spend", params={"months": 24})
    assert category_spend.status_code == 200
    spend_rows = category_spend.json()
    assert len(spend_rows) == 1
    assert spend_rows[0]["category_name"] == "Groceries"
    assert spend_rows[0]["spend_total"] == "42.5000"


def test_duplicate_manual_transaction_conflict(client):
    account, category = _create_setup(client)
    payload = {
        "account_id": account["id"],
        "transaction_date": "2025-04-05",
        "amount": "-42.50",
        "currency": "USD",
        "description": "Whole Foods",
        "category_id": category["id"],
    }

    first = client.post("/transactions", json=payload)
    second = client.post("/transactions", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
