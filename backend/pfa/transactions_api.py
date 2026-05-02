"""HTTP routes for single-transaction drill-down (anomalies slice UI)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pfa.db import connect

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionDetailOut(BaseModel):
    id: UUID
    account_id: UUID
    transaction_date: str
    posted_date: str | None
    amount: Decimal
    currency: str
    description_raw: str
    description_normalized: str
    category_id: UUID | None = None
    category_slug: str | None = None
    category_name: str | None = None


@router.get("/{transaction_id}", response_model=TransactionDetailOut)
def get_transaction(transaction_id: UUID):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.account_id, t.transaction_date, t.posted_date, t.amount,
                   t.currency, t.description_raw, t.description_normalized,
                   t.category_id, c.slug, c.name
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.id = %s
            LIMIT 1
            """,
            (str(transaction_id),),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    pid = row[3]
    return TransactionDetailOut(
        id=row[0],
        account_id=row[1],
        transaction_date=row[2].isoformat(),
        posted_date=pid.isoformat() if pid is not None else None,
        amount=row[4],
        currency=row[5],
        description_raw=row[6],
        description_normalized=row[7],
        category_id=row[8],
        category_slug=row[9],
        category_name=row[10],
    )
