"""Manual transaction entry and explorer routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from pfa.db import connect
from pfa.dedupe import normalize_description, transaction_fingerprint

router = APIRouter(tags=["transactions"])


class TransactionCreate(BaseModel):
    account_id: UUID
    transaction_date: date
    posted_date: date | None = None
    amount: Decimal
    currency: str = Field(default="USD", min_length=1, max_length=8)
    description: str = Field(min_length=1, max_length=512)
    category_id: UUID | None = None


class TransactionOut(BaseModel):
    id: UUID
    account_id: UUID
    account_name: str
    institution_name: str
    transaction_date: date
    posted_date: date | None
    amount: Decimal
    currency: str
    description_raw: str
    category_id: UUID | None
    category_name: str | None


def _ensure_account_exists(conn, account_id: UUID) -> None:
    row = conn.execute("SELECT 1 FROM accounts WHERE id = %s", (str(account_id),)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="account not found")


def _ensure_category_exists(conn, category_id: UUID | None) -> None:
    if category_id is None:
        return
    row = conn.execute("SELECT 1 FROM categories WHERE id = %s", (str(category_id),)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="category not found")


def _list_transactions(
    *,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[dict]:
    sql = """
        SELECT t.id, t.account_id, a.name AS account_name, i.name AS institution_name,
               t.transaction_date, t.posted_date, t.amount, t.currency,
               t.description_raw, t.category_id, c.name AS category_name
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        JOIN institutions i ON i.id = a.institution_id
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE 1 = 1
    """
    params: list[object] = []
    if account_id is not None:
        sql += " AND t.account_id = %s"
        params.append(str(account_id))
    if category_id is not None:
        sql += " AND t.category_id = %s"
        params.append(str(category_id))
    if start_date is not None:
        sql += " AND t.transaction_date >= %s"
        params.append(start_date)
    if end_date is not None:
        sql += " AND t.transaction_date <= %s"
        params.append(end_date)
    if q:
        sql += " AND t.description_raw ILIKE %s"
        params.append(f"%{q.strip()}%")
    sql += " ORDER BY t.transaction_date DESC, t.created_at DESC LIMIT %s"
    params.append(limit)

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]


def _get_transaction_by_id(transaction_id: UUID) -> dict:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT t.id, t.account_id, a.name AS account_name, i.name AS institution_name,
                       t.transaction_date, t.posted_date, t.amount, t.currency,
                       t.description_raw, t.category_id, c.name AS category_name
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                JOIN institutions i ON i.id = a.institution_id
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.id = %s
                LIMIT 1
                """,
                (str(transaction_id),),
            )
            row = cur.fetchone()
    assert row is not None
    return dict(row)


@router.get("/transactions", response_model=list[TransactionOut])
def get_transactions(
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    q: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = _list_transactions(
        account_id=account_id,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        q=q,
        limit=limit,
    )
    return [TransactionOut(**row) for row in rows]


@router.post("/transactions", response_model=TransactionOut)
def post_transaction(body: TransactionCreate):
    desc_norm = normalize_description(body.description)
    fp = transaction_fingerprint(
        body.account_id,
        body.transaction_date,
        body.amount,
        desc_norm,
    )
    with connect() as conn:
        _ensure_account_exists(conn, body.account_id)
        _ensure_category_exists(conn, body.category_id)
        try:
            row = conn.execute(
                """
                INSERT INTO transactions (
                  account_id,
                  transaction_date,
                  posted_date,
                  amount,
                  currency,
                  description_raw,
                  description_normalized,
                  dedupe_fingerprint,
                  category_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    str(body.account_id),
                    body.transaction_date,
                    body.posted_date,
                    body.amount,
                    body.currency.upper(),
                    body.description.strip(),
                    desc_norm,
                    fp,
                    str(body.category_id) if body.category_id else None,
                ),
            ).fetchone()
        except pg_errors.UniqueViolation as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail="transaction already exists") from exc
        conn.commit()
    assert row is not None
    return TransactionOut(**_get_transaction_by_id(row[0]))
