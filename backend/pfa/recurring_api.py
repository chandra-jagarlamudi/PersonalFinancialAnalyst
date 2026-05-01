"""HTTP routes for recurring charge detection (slice 8)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from pfa.db import connect
from pfa.recurring import TxRow, detect_recurring

router = APIRouter(prefix="/recurring", tags=["recurring"])


class RecurringResponse(BaseModel):
    merchant: str
    typical_amount: Decimal
    occurrences: int
    first_seen: datetime.date
    last_seen: datetime.date
    monthly_dates: list[datetime.date]
    category_id: UUID | None


@router.get("", response_model=list[RecurringResponse])
def list_recurring(account_id: UUID | None = None, min_occurrences: int = 3):
    with connect() as conn:
        if account_id is not None:
            rows = conn.execute(
                """
                SELECT id, transaction_date, amount, description_normalized, category_id
                FROM transactions
                WHERE account_id = %s AND amount < 0
                ORDER BY transaction_date
                """,
                (str(account_id),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, transaction_date, amount, description_normalized, category_id
                FROM transactions
                WHERE amount < 0
                ORDER BY transaction_date
                """
            ).fetchall()

    txs = [
        TxRow(
            id=str(r[0]),
            transaction_date=r[1],
            amount=r[2],
            description_normalized=r[3],
            category_id=str(r[4]) if r[4] is not None else None,
        )
        for r in rows
    ]
    return detect_recurring(txs, min_occurrences=min_occurrences)
