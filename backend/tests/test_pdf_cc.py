"""Targeted PDF parse outcomes — extraction + confidence gates."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pfa.csv_parse import ParsedCsvRow
from pfa.pdf_cc import (
    HITL_CONFIDENCE_THRESHOLD,
    outcome_requires_hitl,
    parse_targeted_credit_card_pdf,
    requires_hitl,
    TargetedPdfParseOutcome,
)


def _pdf_bytes_with_lines(lines: list[str]) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in lines:
        pdf.cell(0, 8, text=line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())


def test_parse_capital_one_payments_and_purchases_snippet():
    from pfa.pdf_cc import _parse_capital_one_transactions

    text = (
        "capitalone.com\n"
        "Mar 17, 2026 - Apr 15, 2026\n"
        "Payments, Credits and Adjustments Trans Date Post Date Description Amount "
        "Apr 10 Apr 10 CAPITAL ONE AUTOPAY PYMT - $439.13 "
        "CHANDRA S JAGARLAMUDI #8223: Transactions Trans Date Post Date Description Amount "
        "Apr 1 Apr 2 SCHOOLCAFE855-7292328TX $72.45 Apr 3 Apr 4 COSERV ELECTRICNRC4.COSERV.CTX $130.00 "
        "CHANDRA S JAGARLAMUDI #8223: Total Transactions $202.45 "
    )
    rows = _parse_capital_one_transactions(text)
    assert len(rows) == 3
    autopay = next(r for r in rows if "AUTOPAY" in r.description_raw)
    assert autopay.amount == Decimal("-439.13")
    assert autopay.transaction_date.isoformat() == "2026-04-10"


def test_parse_citi_payment_negative_after_dash_line():
    from pfa.pdf_cc import _parse_citi_transactions

    text = (
        "citicards.com\n"
        "Billing Period: 03/18/26-04/16/26\n"
        "04/14\n"
        "ONLINE PAYMENT, THANK YOU\n"
        "-\n"
        "$879.89\n"
        "03/17\n"
        "03/18\n"
        "SAI SWAGRUHA CURRY POINT 224-3881187  TX\n"
        "$23.77\n"
    )
    rows = _parse_citi_transactions(text)
    assert len(rows) == 2
    pay = next(r for r in rows if "PAYMENT" in r.description_raw.upper())
    assert pay.amount == Decimal("-879.89")


def test_parse_amex_multiline_plaintext_snippet():
    from pfa.pdf_cc import _parse_statement_text

    snippet = """Detail
03/04/26 SPECTRUM MOBILE 855-707-7328 MO
CABLE SVC
$100.00 ⧫
03/04/26 AMAZON MARKETPLACE NA PA AMZN.COM/BILL WA
MERCHANDISE
$20.18 ⧫
03/28/26* MOBILE PAYMENT - THANK YOU -$515.54
"""
    rows = _parse_statement_text(snippet)
    assert len(rows) == 3
    spectrum = next(r for r in rows if "SPECTRUM" in r.description_raw)
    assert spectrum.amount == Decimal("100.00")
    amazon = next(r for r in rows if "AMAZON MARKETPLACE" in r.description_raw)
    assert amazon.amount == Decimal("20.18")
    payment = next(r for r in rows if "MOBILE PAYMENT" in r.description_raw)
    assert payment.amount == Decimal("-515.54")


def test_parse_pdf_extracts_three_transactions_and_auto_passes_hitl_gate():
    raw = _pdf_bytes_with_lines(
        [
            "03/01/2025  COFFEE SHOP  -4.50",
            "03/02/2025  GROCERY INC  -55.12",
            "2025-03-03  PAYROLL DEP  1200.00",
        ]
    )
    out = parse_targeted_credit_card_pdf(raw)
    assert len(out.rows) == 3
    assert out.rows[0].transaction_date == datetime.date(2025, 3, 1)
    assert out.rows[0].amount == Decimal("-4.50")
    assert out.rows[0].description_raw == "COFFEE SHOP"
    assert out.rows[2].transaction_date == datetime.date(2025, 3, 3)
    assert out.rows[2].amount == Decimal("1200.00")
    assert outcome_requires_hitl(out) is False


def test_parse_pdf_two_transactions_stays_below_confidence_threshold():
    raw = _pdf_bytes_with_lines(
        [
            "03/01/2025  COFFEE SHOP  -4.50",
            "03/02/2025  GROCERY INC  -55.12",
        ]
    )
    out = parse_targeted_credit_card_pdf(raw)
    assert len(out.rows) == 2
    assert outcome_requires_hitl(out) is True


def test_parse_pdf_minimal_bytes_without_text_requires_review():
    raw = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj trailer<<>>\n%%EOF\n"
    out = parse_targeted_credit_card_pdf(raw)
    assert out.rows == ()
    assert outcome_requires_hitl(out) is True
    assert "pdf_text_extraction" in out.notes or "pdf_read_error" in out.notes


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


def test_outcome_requires_hitl_honors_threshold_override():
    o = TargetedPdfParseOutcome(
        (
            ParsedCsvRow(
                transaction_date=datetime.date(2025, 1, 1),
                posted_date=None,
                amount=Decimal("-1"),
                currency="USD",
                description_raw="x",
            ),
        ),
        Decimal("0.80"),
        "test",
    )
    assert outcome_requires_hitl(o, threshold=Decimal("0.75")) is False
