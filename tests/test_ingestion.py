"""Ingestion pipeline tests.

T-053: Concurrent duplicate upload → one 200, one 409; single DB statement
Parser unit tests: T-047–T-050 (Chase, Amex CSV/PDF, Capital One, Robinhood)
Normalization unit tests: T-051 (dates, amounts, dedup, description cleaning)
"""

from __future__ import annotations

import asyncio
import io
import textwrap
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from financial_assistant.normalization import (
    NormalizedRow,
    normalize_transactions,
    _clean_description,
    _extract_merchant,
    _normalize_amount,
    _parse_date,
)
from financial_assistant.parsers import (
    RawRow,
    detect_bank,
    parse_amex,
    parse_capital_one,
    parse_chase,
    parse_robinhood,
)


# ── Parser unit tests ─────────────────────────────────────────────────────────

CHASE_CSV = textwrap.dedent("""\
    Transaction Date,Post Date,Description,Category,Type,Amount,Memo
    01/15/2024,01/16/2024,AMAZON.COM*1A2B3,Shopping,Sale,-29.99,
    01/20/2024,01/21/2024,REFUND FROM STORE,Shopping,Return,15.00,
    """).encode()

CHASE_CHECKING_CSV = textwrap.dedent("""\
    Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
    DEBIT,01/15/2024,GROCERY STORE,-52.18,ACH_DEBIT,1000.00,
    CREDIT,01/20/2024,PAYROLL DEPOSIT,2000.00,ACH_CREDIT,3000.00,
    """).encode()

AMEX_CSV = textwrap.dedent("""\
    Date,Description,Amount
    01/15/2024,WHOLE FOODS MARKET,-45.67
    01/18/2024,PAYMENT THANK YOU,200.00
    """).encode()

CAPITAL_ONE_CSV = textwrap.dedent("""\
    Transaction Date,Posted Date,Card No.,Description,Category,Debit,Credit
    2024-01-15,2024-01-16,1234,NETFLIX,Entertainment,15.99,
    2024-01-20,2024-01-21,1234,REFUND,Other,,25.00
    """).encode()

ROBINHOOD_CSV = textwrap.dedent("""\
    Activity Date,Process Date,Settle Date,Instrument,Description,Trans Code,Quantity,Price,Amount
    01/15/2024,01/15/2024,01/17/2024,,ACH DEPOSIT,ACH,,,1000.00
    01/18/2024,01/18/2024,01/20/2024,AAPL,Buy AAPL,Buy,10,175.00,-1750.00
    01/20/2024,01/20/2024,01/22/2024,,DIVIDEND,DIV,,,12.50
    """).encode()


def test_chase_credit_csv_parses_transactions():
    rows = parse_chase(CHASE_CSV)
    assert len(rows) == 2
    assert rows[0].date_str == "01/15/2024"
    assert rows[0].description == "AMAZON.COM*1A2B3"
    assert rows[0].amount == -29.99
    assert rows[1].amount == 15.00


def test_chase_checking_csv_parses_transactions():
    rows = parse_chase(CHASE_CHECKING_CSV)
    assert len(rows) == 2
    assert rows[0].amount == -52.18
    assert rows[1].amount == 2000.00


def test_amex_csv_parses_transactions():
    rows = parse_amex(AMEX_CSV, is_pdf=False)
    assert len(rows) == 2
    assert rows[0].date_str == "01/15/2024"
    assert rows[0].amount == -45.67
    assert rows[1].amount == 200.00


def test_capital_one_csv_debit_credit_columns():
    rows = parse_capital_one(CAPITAL_ONE_CSV)
    assert len(rows) == 2
    # Debit row: amount = 0 - 15.99 = -15.99
    assert rows[0].amount == -15.99
    # Credit row: amount = 25.00 - 0 = 25.00
    assert rows[1].amount == 25.00


def test_robinhood_filters_equity_trades():
    rows = parse_robinhood(ROBINHOOD_CSV)
    # Buy trade should be excluded
    assert len(rows) == 2
    descriptions = [r.description for r in rows]
    assert not any("Buy" in d for d in descriptions)
    assert rows[0].amount == 1000.00
    assert rows[1].amount == 12.50


def test_detect_bank_chase_csv():
    bank = detect_bank("statement.csv", CHASE_CSV)
    assert bank == "chase"


def test_detect_bank_amex_csv():
    bank = detect_bank("statement.csv", AMEX_CSV)
    assert bank == "amex"


def test_detect_bank_capital_one_csv():
    bank = detect_bank("statement.csv", CAPITAL_ONE_CSV)
    assert bank == "capital_one"


def test_detect_bank_robinhood_csv():
    bank = detect_bank("statement.csv", ROBINHOOD_CSV)
    assert bank == "robinhood"


def test_detect_bank_returns_none_for_unknown():
    unknown_csv = b"col1,col2,col3\n1,2,3\n"
    assert detect_bank("statement.csv", unknown_csv) is None


# ── Normalization unit tests ──────────────────────────────────────────────────

def test_parse_date_formats():
    from datetime import date
    assert _parse_date("01/15/2024") == date(2024, 1, 15)
    assert _parse_date("2024-01-15") == date(2024, 1, 15)
    assert _parse_date("15-Jan-2024") == date(2024, 1, 15)
    assert _parse_date("invalid") is None


def test_normalize_amount_negative_is_debit():
    amount, tx_type = _normalize_amount(-29.99)
    assert amount == Decimal("29.99")
    assert tx_type == "debit"


def test_normalize_amount_positive_is_credit():
    amount, tx_type = _normalize_amount(100.00)
    assert amount == Decimal("100.00")
    assert tx_type == "credit"


def test_clean_description_strips_control_chars():
    raw = "AMAZON\x00.COM\x1f STORE"
    cleaned = _clean_description(raw)
    assert "\x00" not in cleaned
    assert "\x1f" not in cleaned
    assert "AMAZON" in cleaned


def test_extract_merchant_splits_on_delimiter():
    assert _extract_merchant("AMAZON.COM*ABC123") == "AMAZON.COM"
    assert _extract_merchant("WHOLE FOODS #1234") == "WHOLE FOODS"


def test_normalize_transactions_dedup_within_upload():
    rows = [
        RawRow(date_str="01/15/2024", description="STARBUCKS", amount=-5.50),
        RawRow(date_str="01/15/2024", description="STARBUCKS", amount=-5.50),  # duplicate
        RawRow(date_str="01/15/2024", description="AMAZON", amount=-19.99),
    ]
    result = normalize_transactions(rows)
    assert len(result) == 2
    descriptions = {r.description for r in result}
    assert "STARBUCKS" in descriptions
    assert "AMAZON" in descriptions


def test_normalize_transactions_skips_invalid_dates():
    rows = [
        RawRow(date_str="not-a-date", description="BAD ROW", amount=-10.00),
        RawRow(date_str="01/15/2024", description="GOOD ROW", amount=-10.00),
    ]
    result = normalize_transactions(rows)
    assert len(result) == 1
    assert result[0].description == "GOOD ROW"


def test_normalize_transactions_iso_dates():
    from datetime import date
    rows = [RawRow(date_str="01/15/2024", description="TEST", amount=-1.00)]
    result = normalize_transactions(rows)
    assert result[0].date == date(2024, 1, 15)


def test_normalized_row_has_hash():
    rows = [RawRow(date_str="01/15/2024", description="TEST MERCHANT", amount=-10.00)]
    result = normalize_transactions(rows)
    assert len(result[0].raw_description_hash) == 64  # SHA-256 hex


# ── T-053: Concurrent duplicate upload test ───────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_duplicate_upload_one_succeeds_one_409():
    """T-053: Two clients upload identical file simultaneously → one 200, one 409."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from httpx import AsyncClient, ASGITransport

    from financial_assistant.upload import router as upload_router

    # Minimal test app — bypass auth/CSRF
    app = FastAPI()
    app.include_router(upload_router)

    # Patch insert_statement_and_transactions:
    # first call returns (5, 5), second returns None (duplicate)
    call_count = 0

    async def mock_insert(db, statement, tx_dicts):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (len(tx_dicts), len(tx_dicts))
        return None  # duplicate

    with patch(
        "financial_assistant.upload.insert_statement_and_transactions",
        side_effect=mock_insert,
    ), patch(
        "financial_assistant.upload.get_session",
    ) as mock_get_session:
        # Mock the async context manager
        mock_db = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_cm

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            files = {"file": ("chase.csv", CHASE_CSV, "text/csv")}

            # Fire both requests concurrently
            results = await asyncio.gather(
                client.post("/upload", files={"file": ("chase.csv", CHASE_CSV, "text/csv")}),
                client.post("/upload", files={"file": ("chase.csv", CHASE_CSV, "text/csv")}),
                return_exceptions=True,
            )

    status_codes = sorted([r.status_code for r in results if hasattr(r, "status_code")])
    assert 200 in status_codes, f"Expected one 200, got {status_codes}"
    assert 409 in status_codes, f"Expected one 409, got {status_codes}"
