"""Setup API: institutions, accounts, account types."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_list_account_types_ordered(client):
    r = client.get("/account-types")
    assert r.status_code == 200
    types = r.json()
    assert len(types) >= 6
    codes = [t["code"] for t in types]
    assert "checking" in codes and "other" in codes


def test_create_account_requires_valid_account_type_id(client):
    inst = client.post("/institutions", json={"name": "T Bank"}).json()
    r = client.post(
        "/accounts",
        json={
            "institution_id": inst["id"],
            "account_type_id": "00000000-0000-4000-8000-000000000001",
            "name": "Nope",
        },
    )
    assert r.status_code == 404


def test_create_account_with_type_returns_label(client):
    inst = client.post("/institutions", json={"name": "U Bank"}).json()
    types = client.get("/account-types").json()
    checking = next(t for t in types if t["code"] == "checking")
    r = client.post(
        "/accounts",
        json={
            "institution_id": inst["id"],
            "account_type_id": checking["id"],
            "name": "Primary",
            "currency": "USD",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["account_type_id"] == checking["id"]
    assert body["account_type_label"] == "Checking"
    assert body["name"] == "Primary"
