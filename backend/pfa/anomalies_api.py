"""HTTP routes for anomaly signals (slice 9)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from pfa.anomalies import AnomalySignal, detect_anomalies, load_expense_window_and_first_seen
from pfa.db import connect

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class AnomalyResponse(BaseModel):
    kind: str
    merchant: str
    detail: str
    transaction_id: str | None
    transaction_date: datetime.date
    amount: Decimal | None


def _signal_to_response(s: AnomalySignal) -> AnomalyResponse:
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
    window_start = anchor - datetime.timedelta(days=lookback_days)
    with connect() as conn:
        txs, first_seen = load_expense_window_and_first_seen(
            conn,
            account_id=account_id,
            window_start=window_start,
            anchor=anchor,
        )
    signals = detect_anomalies(
        txs,
        as_of=anchor,
        lookback_days=lookback_days,
        first_seen_by_merchant=first_seen,
    )
    return [_signal_to_response(s) for s in signals]
