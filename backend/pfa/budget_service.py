"""Persistence and aggregates for envelope budgets."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from pfa.budget_math import linear_project_month_spend, month_date_range

_YEAR_MONTH = re.compile(r"^(?P<y>\d{4})-(?P<m>\d{2})$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BudgetServiceError(ValueError):
    pass


DEFAULT_CATEGORY_ROWS: tuple[tuple[str, str], ...] = (
    ("groceries", "Groceries"),
    ("rent", "Rent"),
    ("utilities", "Utilities"),
    ("transport", "Transport"),
    ("dining", "Dining"),
    ("entertainment", "Entertainment"),
    ("healthcare", "Healthcare"),
    ("income", "Income"),
)


def parse_year_month(value: str) -> date:
    m = _YEAR_MONTH.fullmatch(value.strip())
    if not m:
        raise BudgetServiceError("year_month must be YYYY-MM")
    y = int(m.group("y"))
    mo = int(m.group("m"))
    if mo < 1 or mo > 12:
        raise BudgetServiceError("invalid month in year_month")
    return date(y, mo, 1)


def validate_slug(slug: str) -> None:
    if not _SLUG.fullmatch(slug.strip()):
        raise BudgetServiceError(
            "slug must be lowercase alphanumerics separated by single hyphens "
            "(no leading, trailing, or consecutive hyphens)"
        )


def suggest_history_window(month_start: date, lookback_months: int) -> tuple[date, date]:
    if lookback_months < 1:
        raise BudgetServiceError("lookback_months must be >= 1")
    end = month_start - timedelta(days=1)
    y, m = month_start.year, month_start.month
    m -= lookback_months
    while m <= 0:
        m += 12
        y -= 1
    start = date(y, m, 1)
    return start, end


def create_category(conn: psycopg.Connection, slug: str, name: str) -> UUID:
    validate_slug(slug)
    name = name.strip()
    if not name:
        raise BudgetServiceError("name is required")
    try:
        row = conn.execute(
            "INSERT INTO categories (slug, name) VALUES (%s, %s) RETURNING id",
            (slug.strip(), name),
        ).fetchone()
    except pg_errors.UniqueViolation as e:
        conn.rollback()
        raise BudgetServiceError("category slug already exists") from e
    conn.commit()
    assert row is not None
    return UUID(str(row[0]))


def update_category(conn: psycopg.Connection, category_id: UUID, slug: str, name: str) -> None:
    validate_slug(slug)
    name = name.strip()
    if not name:
        raise BudgetServiceError("name is required")
    try:
        row = conn.execute(
            """
            UPDATE categories
            SET slug = %s, name = %s
            WHERE id = %s
            RETURNING id
            """,
            (slug.strip(), name, str(category_id)),
        ).fetchone()
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        raise BudgetServiceError("category slug already exists") from exc
    if row is None:
        conn.rollback()
        raise BudgetServiceError("category not found")
    conn.commit()


def list_categories(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, slug, name, created_at FROM categories ORDER BY slug ASC"
        )
        return [dict(r) for r in cur.fetchall()]


def bootstrap_default_categories(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        for slug, name in DEFAULT_CATEGORY_ROWS:
            cur.execute(
                """
                INSERT INTO categories (slug, name)
                VALUES (%s, %s)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                """,
                (slug, name),
            )
    conn.commit()
    return list_categories(conn)


def upsert_budgets(
    conn: psycopg.Connection,
    month_start: date,
    items: list[tuple[UUID, Decimal]],
) -> None:
    try:
        with conn.cursor() as cur:
            for cat_id, amount in items:
                if amount < 0:
                    raise BudgetServiceError("budget amount cannot be negative")
                cur.execute("SELECT 1 FROM categories WHERE id = %s", (str(cat_id),))
                if cur.fetchone() is None:
                    raise BudgetServiceError("unknown category_id")
                cur.execute(
                    """
                    INSERT INTO budgets (category_id, month, amount)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (category_id, month)
                    DO UPDATE SET amount = EXCLUDED.amount, updated_at = now()
                    """,
                    (str(cat_id), month_start, amount),
                )
        conn.commit()
    except BudgetServiceError:
        conn.rollback()
        raise


def list_budgets(conn: psycopg.Connection, month_start: date) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT b.category_id, c.slug, c.name, b.amount, b.currency
            FROM budgets b
            JOIN categories c ON c.id = b.category_id
            WHERE b.month = %s
            ORDER BY c.slug ASC
            """,
            (month_start,),
        )
        return [dict(r) for r in cur.fetchall()]


def budget_status(
    conn: psycopg.Connection, month_start: date, as_of: date
) -> list[dict]:
    _, month_end = month_date_range(month_start)
    mtd_end = min(as_of, month_end)
    if as_of < month_start:
        mtd_end = month_start - timedelta(days=1)  # empty MTD window
    out: list[dict] = []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT b.category_id, c.slug, c.name, b.amount AS budget_amount,
              COALESCE(SUM(CASE WHEN t.amount < 0 THEN (-t.amount) ELSE 0 END), 0) AS spent_mtd
            FROM budgets b
            JOIN categories c ON c.id = b.category_id
            LEFT JOIN transactions t
              ON t.category_id = b.category_id
             AND t.transaction_date >= %s
             AND t.transaction_date <= %s
            WHERE b.month = %s
            GROUP BY b.category_id, c.slug, c.name, b.amount
            ORDER BY c.slug ASC
            """,
            (month_start, mtd_end, month_start),
        )
        for row in cur.fetchall():
            spent = Decimal(str(row["spent_mtd"]))
            budget_amt = Decimal(str(row["budget_amount"]))
            projected = linear_project_month_spend(spent, month_start, as_of)
            days_elapsed = 0
            if as_of >= month_start:
                span_end = min(as_of, month_end)
                days_elapsed = (span_end - month_start).days + 1
            dim = (month_end - month_start).days + 1
            out.append(
                {
                    "category_id": row["category_id"],
                    "slug": row["slug"],
                    "name": row["name"],
                    "budget_amount": budget_amt,
                    "spent_mtd": spent,
                    "projected_spend": projected,
                    "remaining_mtd": budget_amt - spent,
                    "remaining_projected": budget_amt - projected,
                    "days_elapsed": days_elapsed,
                    "days_in_month": dim,
                }
            )
    return out


def suggest_budget_amounts(
    conn: psycopg.Connection, month_start: date, lookback_months: int
) -> list[dict]:
    start, end = suggest_history_window(month_start, lookback_months)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT t.category_id, c.slug, c.name,
              SUM(CASE WHEN t.amount < 0 THEN (-t.amount) ELSE 0 END) AS total_spend
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
            WHERE t.transaction_date >= %s AND t.transaction_date <= %s
            GROUP BY t.category_id, c.slug, c.name
            HAVING SUM(CASE WHEN t.amount < 0 THEN (-t.amount) ELSE 0 END) > 0
            ORDER BY c.slug ASC
            """,
            (start, end),
        )
        rows = cur.fetchall()
    denom = Decimal(lookback_months)
    suggestions = []
    for row in rows:
        total = Decimal(str(row["total_spend"]))
        suggested = (total / denom).quantize(Decimal("0.0001"))
        suggestions.append(
            {
                "category_id": row["category_id"],
                "slug": row["slug"],
                "name": row["name"],
                "suggested_amount": suggested,
                "history_total_spend": total,
                "lookback_months": lookback_months,
            }
        )
    return suggestions
