"""Targeted PDF parse outcomes (slice 12) — pure tests."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pfa.csv_parse import ParsedCsvRow
from pfa.pdf_cc import (
    HITL_CONFIDENCE_THRESHOLD,
    outcome_requires_hitl,
    parse_targeted_credit_card_pdf_stub,
    requires_hitl,
    TargetedPdfParseOutcome,
)


def test_stub_parser_low_confidence_empty_rows():
    out = parse_targeted_credit_card_pdf_stub(b"%PDF-1.4\n")
    assert out.rows == ()
    assert out.confidence == Decimal("0.35")
    assert outcome_requires_hitl(out) is True


def test_outcome_requires_hitl_when_high_confidence_but_no_rows():
    o = TargetedPdfParseOutcome((), Decimal("0.95"), "test")
    assert outcome_requires_hitl(o) is True


def test_outcome_allows_auto_when_confident_and_rows():
    row = ParsedCsvRow(
        transaction_date=datetime.date(2025, 1, 1),
        posted_date=None,
        amount=Decimal("-1"),
        currency="USD",
        description_raw="x",
    )
    o = TargetedPdfParseOutcome((row,), Decimal("0.95"), "test")
    assert outcome_requires_hitl(o) is False


def test_requires_hitl_threshold_boundary():
    assert requires_hitl(HITL_CONFIDENCE_THRESHOLD - Decimal("0.01")) is True
    assert requires_hitl(HITL_CONFIDENCE_THRESHOLD) is False
