"""Dedupe fingerprint behavior (pure functions)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pfa.dedupe import normalize_description, transaction_fingerprint


def test_fingerprint_is_stable_for_same_logical_transaction():
    aid = UUID("11111111-1111-1111-1111-111111111111")
    d = date(2025, 3, 15)
    fp1 = transaction_fingerprint(
        aid, d, date(2025, 3, 16), Decimal("-42.50"), "coffee shop"
    )
    fp2 = transaction_fingerprint(
        aid, d, date(2025, 3, 16), Decimal("-42.50"), "coffee shop"
    )
    assert fp1 == fp2
    assert len(fp1) == 64


def test_fingerprint_changes_when_amount_changes():
    aid = UUID("22222222-2222-2222-2222-222222222222")
    d = date(2025, 1, 1)
    a = transaction_fingerprint(aid, d, None, Decimal("10.00"), "paycheck")
    b = transaction_fingerprint(aid, d, None, Decimal("10.01"), "paycheck")
    assert a != b


def test_normalize_description_collapses_whitespace_and_case():
    assert normalize_description("  Foo   BAR ") == "foo bar"


def test_fingerprint_treats_missing_posted_date_consistently():
    aid = UUID("33333333-3333-3333-3333-333333333333")
    d = date(2025, 6, 1)
    with_posted = transaction_fingerprint(
        aid, d, date(2025, 6, 2), Decimal("1"), "x"
    )
    without_posted = transaction_fingerprint(aid, d, None, Decimal("1"), "x")
    assert with_posted != without_posted
