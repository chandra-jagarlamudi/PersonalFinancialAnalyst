"""CSV statement parsing (public parse API)."""

from decimal import Decimal

import pytest

from pfa.csv_parse import CsvParseError, parse_csv_bytes


def test_parse_minimal_headers_iso_dates():
    body = (
        "transaction_date,amount,description\n"
        "2025-03-01,-12.34,GROCERY STORE\n"
        "2025-03-02,100.00,PAYROLL\n"
    ).encode()
    rows = parse_csv_bytes(body)
    assert len(rows) == 2
    assert rows[0].transaction_date.isoformat() == "2025-03-01"
    assert rows[0].amount == Decimal("-12.34")
    assert rows[0].description_raw == "GROCERY STORE"
    assert rows[0].posted_date is None
    assert rows[1].amount == Decimal("100.00")


def test_parse_optional_posted_date_and_currency():
    body = (
        "transaction_date,posted_date,amount,currency,description\n"
        "2025-03-01,2025-03-03,-5,EUR,CAFE\n"
    ).encode()
    rows = parse_csv_bytes(body)
    assert rows[0].posted_date.isoformat() == "2025-03-03"
    assert rows[0].currency == "EUR"


def test_parse_strips_currency_decorations_on_amount():
    body = "transaction_date,amount,description\n2025-03-01,\"$1,234.50\",X\n".encode()
    rows = parse_csv_bytes(body)
    assert rows[0].amount == Decimal("1234.50")


def test_parse_utf8_bom_ignored():
    body = "transaction_date,amount,description\n2025-03-01,-1,A\n".encode(
        "utf-8-sig"
    )
    rows = parse_csv_bytes(body)
    assert len(rows) == 1


def test_parse_requires_core_columns():
    body = "transaction_date,description\n2025-03-01,X\n".encode()
    with pytest.raises(CsvParseError, match="amount"):
        parse_csv_bytes(body)
