"""Deterministic transaction fingerprint for cross-statement dedupe."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from uuid import UUID


def normalize_description(raw: str) -> str:
    return " ".join(raw.strip().lower().split())


def transaction_fingerprint(
    account_id: UUID,
    transaction_date: date,
    posted_date: date | None,
    amount: Decimal,
    description_normalized: str,
) -> str:
    posted = posted_date.isoformat() if posted_date else ""
    canonical = "|".join(
        (
            str(account_id),
            transaction_date.isoformat(),
            posted,
            f"{amount.quantize(Decimal('0.0001')):.4f}",
            description_normalized,
        )
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
