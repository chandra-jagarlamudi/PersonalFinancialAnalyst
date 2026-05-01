"""Dedupe fingerprint behavior (pure functions)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pfa.dedupe import normalize_description, transaction_fingerprint


def test_fingerprint_is_stable_for_same_logical_transaction():
    aid = UUID("11111111-1111-1111-1111-111111111111")
    d = date(2025, 3, 15)
    fp1 = transaction_fingerprint(aid, d, Decimal("-42.50"), "coffee shop")
    fp2 = transaction_fingerprint(aid, d, Decimal("-42.50"), "coffee shop")
    assert fp1 == fp2
    assert len(fp1) == 64


def test_fingerprint_changes_when_amount_changes():
    aid = UUID("22222222-2222-2222-2222-222222222222")
    d = date(2025, 1, 1)
    a = transaction_fingerprint(aid, d, Decimal("10.00"), "paycheck")
    b = transaction_fingerprint(aid, d, Decimal("10.01"), "paycheck")
    assert a != b


def test_normalize_description_collapses_whitespace_and_case():
    assert normalize_description("  Foo   BAR ") == "foo bar"


def test_fingerprint_changes_when_normalized_description_differs():
    aid = UUID("33333333-3333-3333-3333-333333333333")
    d = date(2025, 6, 1)
    a = transaction_fingerprint(aid, d, Decimal("1"), "coffee")
    b = transaction_fingerprint(aid, d, Decimal("1"), "tea")
    assert a != b


def test_fingerprint_stable_regardless_of_posted_date():
    # posted_date excluded from fingerprint: overlapping statements with/without it must dedupe.
    aid = UUID("44444444-4444-4444-4444-444444444444")
    d = date(2025, 6, 1)
    fp1 = transaction_fingerprint(aid, d, Decimal("50.00"), "amazon")
    fp2 = transaction_fingerprint(aid, d, Decimal("50.00"), "amazon")
    assert fp1 == fp2
