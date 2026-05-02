"""Ledger bootstrap HTTP API tests."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_setup_bootstrap_flow(client):
    institution = client.post("/institutions", json={"name": "Chase"})
    assert institution.status_code == 200
    institution_id = institution.json()["id"]

    listed_institutions = client.get("/institutions")
    assert listed_institutions.status_code == 200
    assert listed_institutions.json()[0]["name"] == "Chase"

    update_institution = client.put(
        f"/institutions/{institution_id}",
        json={"name": "Chase Personal"},
    )
    assert update_institution.status_code == 204

    account = client.post(
        "/accounts",
        json={
            "institution_id": institution_id,
            "name": "Checking",
            "currency": "usd",
        },
    )
    assert account.status_code == 200
    account_body = account.json()
    assert account_body["currency"] == "USD"
    assert account_body["institution_name"] == "Chase Personal"

    update_account = client.put(
        f"/accounts/{account_body['id']}",
        json={
            "institution_id": institution_id,
            "name": "Everyday Checking",
            "currency": "USD",
        },
    )
    assert update_account.status_code == 204

    alias = client.post(
        "/account-aliases",
        json={"account_id": account_body["id"], "alias": "Chase Checking"},
    )
    assert alias.status_code == 200
    assert alias.json()["account_name"] == "Everyday Checking"

    aliases = client.get("/account-aliases")
    assert aliases.status_code == 200
    assert aliases.json()[0]["alias"] == "Chase Checking"


def test_bootstrap_default_categories_and_update_category(client):
    seeded = client.post("/categories/bootstrap-defaults")
    assert seeded.status_code == 200
    rows = seeded.json()
    assert any(row["slug"] == "groceries" for row in rows)

    groceries = next(row for row in rows if row["slug"] == "groceries")
    update = client.put(
        f"/categories/{groceries['id']}",
        json={"slug": "groceries-home", "name": "Groceries at Home"},
    )
    assert update.status_code == 204

    listed = client.get("/categories")
    assert any(row["slug"] == "groceries-home" for row in listed.json())


def test_duplicate_account_alias_conflict(client, clean_db):
    institution = client.post("/institutions", json={"name": "Local Bank"}).json()
    account = client.post(
        "/accounts",
        json={
            "institution_id": institution["id"],
            "name": "Checking",
            "currency": "USD",
        },
    ).json()

    first = client.post(
        "/account-aliases",
        json={"account_id": account["id"], "alias": "Main Checking"},
    )
    second = client.post(
        "/account-aliases",
        json={"account_id": account["id"], "alias": "Main Checking"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
