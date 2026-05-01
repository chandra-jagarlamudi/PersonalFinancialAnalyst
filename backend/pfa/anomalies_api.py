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


def _signal_to_response(s: AnomalySignal) -> AnomalyResponse:
    return AnomalyResponse(
        kind=s.kind,
        merchant=s.merchant,
        detail=s.detail,
        transaction_id=s.transaction_id,
        transaction_date=s.transaction_date,
        amount=s.amount,
    )


def _load_window_and_first_seen(
    conn,
    *,
    account_id: UUID | None,
    window_start: datetime.date,
    anchor: datetime.date,
) -> tuple[list[TxRow], dict[str, datetime.date]]:
    """In-window expense rows + global first spend date per merchant appearing in that window."""
    if account_id is not None:
        aid = str(account_id)
        rows = conn.execute(
            """
            SELECT id, transaction_date, amount, description_normalized, category_id
            FROM transactions
            WHERE account_id = %s::uuid
              AND amount < 0
              AND transaction_date >= %s
              AND transaction_date <= %s
            ORDER BY transaction_date
            """,
            (aid, window_start, anchor),
        ).fetchall()
        first_seen_rows = conn.execute(
            """
            WITH mer AS (
              SELECT DISTINCT description_normalized AS d
              FROM transactions
              WHERE account_id = %s::uuid
                AND amount < 0
                AND transaction_date >= %s
                AND transaction_date <= %s
            )
            SELECT t.description_normalized, MIN(t.transaction_date)
            FROM transactions t
            INNER JOIN mer ON mer.d = t.description_normalized
            WHERE t.account_id = %s::uuid AND t.amount < 0
            GROUP BY t.description_normalized
            """,
            (aid, window_start, anchor, aid),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, transaction_date, amount, description_normalized, category_id
            FROM transactions
            WHERE amount < 0
              AND transaction_date >= %s
              AND transaction_date <= %s
            ORDER BY transaction_date
            """,
            (window_start, anchor),
        ).fetchall()
        first_seen_rows = conn.execute(
            """
            WITH mer AS (
              SELECT DISTINCT description_normalized AS d
              FROM transactions
              WHERE amount < 0
                AND transaction_date >= %s
                AND transaction_date <= %s
            )
            SELECT t.description_normalized, MIN(t.transaction_date)
            FROM transactions t
            INNER JOIN mer ON mer.d = t.description_normalized
            WHERE t.amount < 0
            GROUP BY t.description_normalized
            """,
            (window_start, anchor),
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
    first_seen: dict[str, datetime.date] = {str(r[0]): r[1] for r in first_seen_rows}
    return txs, first_seen


@router.get("", response_model=list[AnomalyResponse])
def list_anomalies(
    account_id: UUID | None = None,
    as_of: datetime.date | None = None,
    lookback_days: Annotated[int, Query(ge=1, le=730)] = 120,
):
    anchor = as_of or datetime.date.today()
    window_start = anchor - datetime.timedelta(days=lookback_days)
    with connect() as conn:
        txs, first_seen = _load_window_and_first_seen(
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
