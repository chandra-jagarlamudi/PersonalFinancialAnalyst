"""HTTP routes for anomaly signals (slice 9)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from pfa.anomalies import AnomalySignal, detect_anomalies
from pfa.db import connect
from pfa.recurring import TxRow

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class AnomalyResponse(BaseModel):
    kind: str
    merchant: str
    detail: str
    transaction_id: str | None
    transaction_date: datetime.date
    amount: Decimal | None


def _row_to_signal(s: AnomalySignal) -> AnomalyResponse:
    return AnomalyResponse(
        kind=s.kind,
        merchant=s.merchant,
        detail=s.detail,
        transaction_id=s.transaction_id,
        transaction_date=s.transaction_date,
        amount=s.amount,
    )


@router.get("", response_model=list[AnomalyResponse])
def list_anomalies(
    account_id: UUID | None = None,
    as_of: datetime.date | None = None,
    lookback_days: Annotated[int, Query(ge=1, le=730)] = 120,
):
    anchor = as_of or datetime.date.today()
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
    signals = detect_anomalies(txs, as_of=anchor, lookback_days=lookback_days)
    return [_row_to_signal(s) for s in signals]
