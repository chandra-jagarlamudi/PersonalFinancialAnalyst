"""Dashboard aggregate routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from pfa.db import connect

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _month_window(months: int) -> tuple[date, date]:
    if months < 1:
        raise ValueError("months must be >= 1")
    today = date.today()
    y = today.year
    m = today.month - (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), today


class CashflowPoint(BaseModel):
    month: date
    income_total: Decimal
    expense_total_abs: Decimal
    net_total: Decimal


class CategorySpendPoint(BaseModel):
    month: date
    category_id: str | None
    category_name: str
    spend_total: Decimal


@router.get("/cashflow", response_model=list[CashflowPoint])
def get_cashflow(months: int = Query(default=6, ge=1, le=60)):
    start_date, end_date = _month_window(months)
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT date_trunc('month', transaction_date)::date AS month,
                       COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income_total,
                       COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expense_total_abs,
                       COALESCE(SUM(amount), 0) AS net_total
                FROM transactions
                WHERE transaction_date >= %s AND transaction_date <= %s
                GROUP BY month
                ORDER BY month ASC
                """,
                (start_date, end_date),
            )
            return [CashflowPoint(**dict(row)) for row in cur.fetchall()]


@router.get("/category-spend", response_model=list[CategorySpendPoint])
def get_category_spend(months: int = Query(default=6, ge=1, le=60)):
    start_date, end_date = _month_window(months)
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT date_trunc('month', t.transaction_date)::date AS month,
                       t.category_id::text AS category_id,
                       COALESCE(c.name, 'Uncategorized') AS category_name,
                       COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS spend_total
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.transaction_date >= %s AND t.transaction_date <= %s
                GROUP BY month, t.category_id, category_name
                HAVING COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) > 0
                ORDER BY month ASC, category_name ASC
                """,
                (start_date, end_date),
            )
            return [CategorySpendPoint(**dict(row)) for row in cur.fetchall()]
