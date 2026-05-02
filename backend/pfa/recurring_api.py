"""HTTP routes for recurring charge detection (slice 8)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from pfa.db import connect
from pfa.recurring import TxRow, detect_recurring

router = APIRouter(prefix="/recurring", tags=["recurring"])


class SupportingTxResponse(BaseModel):
    id: str
    transaction_date: datetime.date
    amount: Decimal
    description: str


class RecurringResponse(BaseModel):
    merchant: str
    typical_amount: Decimal
    occurrences: int
    first_seen: datetime.date
    last_seen: datetime.date
    monthly_dates: list[datetime.date]
    category_id: UUID | None
    cadence: str
    supporting_transactions: list[SupportingTxResponse]


@router.get("", response_model=list[RecurringResponse])
def list_recurring(
    account_id: UUID | None = None,
    min_occurrences: Annotated[
        int,
        Query(
            ge=3,
            le=120,
            description="Minimum charges for the same merchant to qualify (product rule: ≥3)",
        ),
    ] = 3,
):
    with connect() as conn:
        if account_id is not None:
            rows = conn.execute(
                """
                SELECT id, transaction_date, amount, description_normalized, category_id,
                       description_raw
                FROM transactions
                WHERE account_id = %s AND amount < 0
                ORDER BY transaction_date
                """,
                (str(account_id),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, transaction_date, amount, description_normalized, category_id,
                       description_raw
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
            description_raw=r[5],
        )
        for r in rows
    ]
    return detect_recurring(txs, min_occurrences=min_occurrences)
