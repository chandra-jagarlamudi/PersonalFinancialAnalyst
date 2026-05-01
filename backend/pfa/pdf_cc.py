"""Targeted credit-card PDF parse ladder (slice 12) — stub + confidence for HITL gate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pfa.csv_parse import ParsedCsvRow

HITL_CONFIDENCE_THRESHOLD = Decimal("0.85")


@dataclass(frozen=True, slots=True)
class TargetedPdfParseOutcome:
    rows: tuple[ParsedCsvRow, ...]
    confidence: Decimal
    notes: str


def parse_targeted_credit_card_pdf_stub(raw: bytes) -> TargetedPdfParseOutcome:
    """Placeholder until the institution-specific parser ships (table → text → OCR ladder)."""
    _ = raw
    return TargetedPdfParseOutcome(
        (),
        Decimal("0.35"),
        "stub_parser_v0:no_rows",
    )


def requires_hitl(confidence: Decimal, *, threshold: Decimal = HITL_CONFIDENCE_THRESHOLD) -> bool:
    return confidence < threshold


def outcome_requires_hitl(outcome: TargetedPdfParseOutcome) -> bool:
    """Human review when confidence is low or the parser produced no rows to persist."""
    if outcome.confidence < HITL_CONFIDENCE_THRESHOLD:
        return True
    return len(outcome.rows) == 0
