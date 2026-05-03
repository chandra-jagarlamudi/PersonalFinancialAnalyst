"""Ledger row normalization before INSERT."""

from datetime import date
from decimal import Decimal

from pfa.csv_parse import ParsedCsvRow
from pfa.ingest import normalize_parsed_row_for_db


def test_normalizes_amount_currency_description():
    row = ParsedCsvRow(
        transaction_date=date(2025, 3, 1),
        posted_date=None,
        amount=Decimal("-12.34001"),
        currency=" eur ",
        description_raw="  MERCHANT  ",
    )
    out = normalize_parsed_row_for_db(row)
    assert out.amount == Decimal("-12.3400")
    assert out.currency == "EUR"
    assert out.description_raw == "MERCHANT"
    assert out.transaction_date == date(2025, 3, 1)


def test_empty_currency_defaults_usd():
    row = ParsedCsvRow(
        transaction_date=date(2025, 1, 1),
        posted_date=None,
        amount=Decimal("1"),
        currency="   ",
        description_raw="x",
    )
    assert normalize_parsed_row_for_db(row).currency == "USD"
