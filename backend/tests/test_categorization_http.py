"""HTTP integration tests for GET /transactions and category correction (slice 7)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_CSV = (
    b"transaction_date,amount,description\n"
    b"2025-01-01,-10.00,GROCERY STORE\n"
    b"2025-01-02,-5.00,COFFEE SHOP\n"
)


def _ingest(client, account_id):
    r = client.post(
        "/ingest/csv",
        data={"account_id": str(account_id)},
        files={"file": ("t.csv", _CSV, "text/csv")},
    )
    assert r.status_code == 200


def _create_category(client, slug: str, name: str) -> str:
    r = client.post("/categories", json={"slug": slug, "name": name})
    assert r.status_code == 200
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Test 1: empty list when no transactions exist
# ---------------------------------------------------------------------------


def test_list_transactions_empty(client, sample_account_id, upload_dir):
    r = client.get("/transactions", params={"account_id": str(sample_account_id)})
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Test 2: two rows returned after CSV ingest with correct fields
# ---------------------------------------------------------------------------


def test_list_transactions_after_ingest(client, sample_account_id, upload_dir):
    _ingest(client, sample_account_id)
    r = client.get("/transactions", params={"account_id": str(sample_account_id)})
    assert r.status_code == 200
    body = r.json()
    rows = body["items"]
    assert body["total"] == 2
    assert len(rows) == 2

    # Ordered by transaction_date DESC → 2025-01-02 first
    assert rows[0]["transaction_date"] == "2025-01-02"
    assert rows[1]["transaction_date"] == "2025-01-01"

    row = rows[0]
    assert "id" in row
    assert "account_id" in row
    assert row["account_id"] == str(sample_account_id)
    assert "amount" in row
    assert "description_raw" in row
    assert "description_normalized" in row
    assert "category_id" in row
    assert row["category_id"] is None
    assert "category_name" in row
    assert row["category_name"] is None
    assert "created_at" in row
    assert row["source_statement_filename"] == "t.csv"


# ---------------------------------------------------------------------------
# Test 3: uncategorized=true returns only uncategorized rows
# ---------------------------------------------------------------------------


def test_list_transactions_uncategorized_filter(client, sample_account_id, upload_dir):
    _ingest(client, sample_account_id)
    r = client.get("/transactions", params={"uncategorized": "true"})
    assert r.status_code == 200
    body = r.json()
    rows = body["items"]
    assert body["total"] == 2
    assert len(rows) == 2
    assert all(row["category_id"] is None for row in rows)


# ---------------------------------------------------------------------------
# Test 4: categorized tx excluded from uncategorized=true list
# ---------------------------------------------------------------------------


def test_list_transactions_uncategorized_filter_excludes_categorized(
    client, sample_account_id, upload_dir
):
    _ingest(client, sample_account_id)
    cid = _create_category(client, "groceries", "Groceries")

    all_body = client.get("/transactions", params={"account_id": str(sample_account_id)}).json()
    all_txs = all_body["items"]
    assert all_body["total"] == 2
    assert len(all_txs) == 2
    tx_to_categorize = all_txs[0]["id"]

    # Correct category on one transaction
    r = client.put(f"/transactions/{tx_to_categorize}/category", json={"category_id": cid})
    assert r.status_code == 200

    uncategorized = client.get(
        "/transactions",
        params={"account_id": str(sample_account_id), "uncategorized": "true"},
    ).json()
    assert uncategorized["total"] == 1
    assert len(uncategorized["items"]) == 1
    assert uncategorized["items"][0]["id"] != tx_to_categorize


# ---------------------------------------------------------------------------
# Test 5: PUT /transactions/{id}/category reflected in GET /transactions list
# ---------------------------------------------------------------------------


def test_update_category_reflected_in_list(client, sample_account_id, upload_dir):
    _ingest(client, sample_account_id)
    cid = _create_category(client, "coffee", "Coffee")

    all_body = client.get("/transactions", params={"account_id": str(sample_account_id)}).json()
    all_txs = all_body["items"]
    # coffee shop is the row with the lower amount (-5.00), date 2025-01-02 → first row (DESC order)
    coffee_tx = all_txs[0]
    assert "COFFEE" in coffee_tx["description_raw"].upper()

    r = client.put(f"/transactions/{coffee_tx['id']}/category", json={"category_id": cid})
    assert r.status_code == 200

    updated = client.get("/transactions", params={"account_id": str(sample_account_id)}).json()
    coffee_updated = next(tx for tx in updated["items"] if tx["id"] == coffee_tx["id"])
    assert coffee_updated["category_id"] == cid
    assert coffee_updated["category_name"] == "Coffee"


# ---------------------------------------------------------------------------
# Test 6: POST /transactions/{id}/suggest-category (mocked LLM)
# ---------------------------------------------------------------------------


def test_suggest_category_returns_match(monkeypatch, client, sample_account_id, upload_dir):
    import pfa.categorization_api as capi

    _ingest(client, sample_account_id)
    cid = _create_category(client, "coffee", "Coffee")

    all_body = client.get("/transactions", params={"account_id": str(sample_account_id)}).json()
    tx_id = all_body["items"][0]["id"]

    monkeypatch.setattr(capi, "suggest_category_slug", lambda **kw: ("coffee", None))

    r = client.post(f"/transactions/{tx_id}/suggest-category")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert body["slug"] == "coffee"
    assert body["category_id"] == cid


def test_suggest_category_without_api_key_returns_error_body(
    monkeypatch, client, sample_account_id, upload_dir
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    _ingest(client, sample_account_id)
    all_body = client.get("/transactions", params={"account_id": str(sample_account_id)}).json()
    tx_id = all_body["items"][0]["id"]

    r = client.post(f"/transactions/{tx_id}/suggest-category")
    assert r.status_code == 200
    body = r.json()
    assert body["category_id"] is None
    assert body["slug"] is None
    assert body["error"] is not None
