"""Transaction normalization pipeline.

T-051: ISO 8601 dates, positive amount + transaction_type direction,
description cleaning, merchant heuristic, intra-upload dedup.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from financial_assistant.parsers import RawRow

_MERCHANT_DELIMITERS = re.compile(r"[*#\-/\\|]+")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_DATE_FORMATS = [
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%b %d, %Y",
]


@dataclass
class NormalizedRow:
    date: date
    description: str
    merchant: str
    amount: Decimal
    transaction_type: str  # "debit" | "credit"
    category: Optional[str]
    raw_description_hash: str  # SHA-256 hex, 64 chars


def normalize_transactions(rows: list[RawRow]) -> list[NormalizedRow]:
    """T-051: Normalize raw rows; deduplicate within this upload."""
    seen: set[tuple] = set()
    result: list[NormalizedRow] = []

    for row in rows:
        parsed_date = _parse_date(row.date_str)
        if parsed_date is None:
            continue

        description = _clean_description(row.description)
        if not description:
            continue

        amount, tx_type = _normalize_amount(row.amount)

        merchant = _extract_merchant(description)
        category = row.category.strip() if row.category else None
        raw_hash = _hash_description(description)

        # Intra-upload dedup on (date, amount, description)
        dedup_key = (parsed_date, amount, description)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        result.append(
            NormalizedRow(
                date=parsed_date,
                description=description,
                merchant=merchant,
                amount=amount,
                transaction_type=tx_type,
                category=category,
                raw_description_hash=raw_hash,
            )
        )

    return result


def _parse_date(date_str: str) -> Optional[date]:
    from datetime import datetime

    s = date_str.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _clean_description(raw: str) -> str:
    # Remove control characters
    cleaned = _CONTROL_CHARS.sub("", raw)
    # Normalize unicode whitespace
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def _normalize_amount(raw: float) -> tuple[Decimal, str]:
    """Return (positive Decimal, transaction_type)."""
    try:
        d = Decimal(str(raw)).quantize(Decimal("0.01"))
    except InvalidOperation:
        d = Decimal("0.00")

    if d < 0:
        return -d, "debit"
    return d, "credit"


def _extract_merchant(description: str) -> str:
    """Heuristic: first meaningful segment before a delimiter."""
    # Split on common delimiter chars
    parts = _MERCHANT_DELIMITERS.split(description, maxsplit=1)
    merchant = parts[0].strip()
    # Truncate to 100 chars for reasonable merchant name length
    return merchant[:100] if merchant else description[:100]


def _hash_description(description: str) -> str:
    """SHA-256 hex of the cleaned description, yielding 64-char hash."""
    return hashlib.sha256(description.encode("utf-8")).hexdigest()
