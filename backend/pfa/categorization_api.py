"""HTTP routes for categorization rules, manual corrections, and rule proposals (slice 7)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from pfa.budget_service import list_categories
from pfa.categorization import apply_rules_retroactively
from pfa.db import connect
from pfa.llm_category_suggest import suggest_category_slug

router = APIRouter(tags=["categorization"])


class RuleCreate(BaseModel):
    category_id: UUID
    pattern: str = Field(min_length=1, max_length=500)
    priority: int = Field(default=100)
    apply_retroactively: bool = False


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    category_name: str
    pattern: str
    priority: int


class CategoryPatch(BaseModel):
    category_id: UUID


class TransactionOut(BaseModel):
    id: UUID
    category_id: UUID | None


class TransactionListItem(BaseModel):
    id: UUID
    account_id: UUID
    transaction_date: datetime.date
    amount: Decimal
    description_raw: str
    description_normalized: str
    category_id: UUID | None
    category_name: str | None
    source_statement_filename: str | None
    created_at: datetime.datetime


class TransactionListPage(BaseModel):
    items: list[TransactionListItem]
    total: int


class CategorySuggestionOut(BaseModel):
    category_id: UUID | None
    slug: str | None
    error: str | None


TransactionSort = Literal[
    "date_desc",
    "date_asc",
    "amount_desc",
    "amount_asc",
    "description_asc",
    "description_desc",
    "category_asc",
    "category_desc",
]


def _order_by_clause(sort: TransactionSort) -> str:
    return {
        "date_desc": "t.transaction_date DESC, t.created_at DESC",
        "date_asc": "t.transaction_date ASC, t.created_at ASC",
        "amount_desc": "t.amount DESC",
        "amount_asc": "t.amount ASC",
        "description_asc": "t.description_normalized ASC",
        "description_desc": "t.description_normalized DESC",
        "category_asc": "COALESCE(c.name, '') ASC",
        "category_desc": "COALESCE(c.name, '') DESC",
    }[sort]


class RuleProposalIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    apply_retroactively: bool = False


class RuleProposalOut(BaseModel):
    proposed_rule: dict
    would_affect_count: int


def _validate_postgres_regex(conn: psycopg.Connection, pattern: str) -> None:
    """Raise 422 if Postgres rejects the pattern (avoids Python/Postgres engine mismatch)."""
    try:
        conn.execute("SELECT '' ~* %s", (pattern,))
    except psycopg.errors.InvalidRegularExpression as exc:
        conn.rollback()
        raise HTTPException(status_code=422, detail=f"invalid regex: {exc}") from exc


@router.get("/categorization/rules", response_model=list[RuleOut])
def list_rules():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.category_id, c.name, r.pattern, r.priority
            FROM categorization_rules r
            JOIN categories c ON c.id = r.category_id
            ORDER BY r.priority ASC, r.created_at ASC
            """
        ).fetchall()
    return [
        RuleOut(id=r[0], category_id=r[1], category_name=r[2], pattern=r[3], priority=r[4])
        for r in rows
    ]


@router.post("/categorization/rules", response_model=RuleOut, status_code=201)
def create_rule(body: RuleCreate):
    with connect() as conn:
        _validate_postgres_regex(conn, body.pattern)

        cat = conn.execute(
            "SELECT id, name FROM categories WHERE id = %s", (str(body.category_id),)
        ).fetchone()
        if cat is None:
            raise HTTPException(status_code=404, detail="category not found")

        row = conn.execute(
            """
            INSERT INTO categorization_rules (category_id, pattern, priority)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (str(body.category_id), body.pattern, body.priority),
        ).fetchone()
        rule_id = row[0]

        if body.apply_retroactively:
            apply_rules_retroactively(conn, str(rule_id))

        conn.commit()

    return RuleOut(
        id=rule_id,
        category_id=body.category_id,
        category_name=cat[1],
        pattern=body.pattern,
        priority=body.priority,
    )


@router.delete("/categorization/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: UUID):
    with connect() as conn:
        result = conn.execute(
            "DELETE FROM categorization_rules WHERE id = %s RETURNING id",
            (str(rule_id),),
        ).fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail="rule not found")
        conn.commit()


@router.put("/transactions/{transaction_id}/category", response_model=TransactionOut)
def update_transaction_category(transaction_id: UUID, body: CategoryPatch):
    with connect() as conn:
        cat = conn.execute(
            "SELECT id FROM categories WHERE id = %s", (str(body.category_id),)
        ).fetchone()
        if cat is None:
            raise HTTPException(status_code=404, detail="category not found")

        result = conn.execute(
            "UPDATE transactions SET category_id = %s WHERE id = %s RETURNING id, category_id",
            (str(body.category_id), str(transaction_id)),
        ).fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        conn.commit()

    return TransactionOut(id=result[0], category_id=result[1])


@router.post("/transactions/{transaction_id}/suggest-category", response_model=CategorySuggestionOut)
def suggest_category_for_transaction(transaction_id: UUID):
    with connect() as conn:
        tx = conn.execute(
            """
            SELECT description_raw, description_normalized
            FROM transactions WHERE id = %s
            """,
            (str(transaction_id),),
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        cats = list_categories(conn)

    slug, err = suggest_category_slug(
        description_raw=tx[0],
        description_normalized=tx[1],
        categories=cats,
    )
    if err or not slug:
        return CategorySuggestionOut(category_id=None, slug=None, error=err or "no suggestion")
    match = next((c for c in cats if c["slug"] == slug), None)
    if match is None:
        return CategorySuggestionOut(category_id=None, slug=None, error="slug not found after validation")
    return CategorySuggestionOut(category_id=UUID(str(match["id"])), slug=slug, error=None)


@router.post("/transactions/{transaction_id}/rule-proposal", response_model=RuleProposalOut)
def propose_rule(transaction_id: UUID, body: RuleProposalIn):
    with connect() as conn:
        tx = conn.execute(
            "SELECT id FROM transactions WHERE id = %s", (str(transaction_id),)
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")

        _validate_postgres_regex(conn, body.pattern)

        if body.apply_retroactively:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL AND description_normalized ~* %s",
                (body.pattern,),
            ).fetchone()
            would_affect = count_row[0] if count_row else 0
        else:
            would_affect = 0

    return RuleProposalOut(
        proposed_rule={"pattern": body.pattern, "apply_retroactively": body.apply_retroactively},
        would_affect_count=would_affect,
    )


@router.get("/transactions", response_model=TransactionListPage)
def list_transactions(
    account_id: Annotated[UUID | None, Query()] = None,
    uncategorized: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[TransactionSort, Query()] = "date_desc",
):
    conditions = []
    params: list = []

    if account_id is not None:
        conditions.append("t.account_id = %s")
        params.append(str(account_id))

    if uncategorized:
        conditions.append("t.category_id IS NULL")

    if q is not None and (stripped := q.strip()):
        conditions.append(
            "(t.description_normalized ILIKE %s OR t.description_raw ILIKE %s)"
        )
        term = f"%{stripped}%"
        params.extend([term, term])

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    order_sql = _order_by_clause(sort)

    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN statements s ON s.id = t.source_statement_id
        {where_clause}
    """

    data_sql = f"""
        SELECT t.id, t.account_id, t.transaction_date, t.amount,
               t.description_raw, t.description_normalized,
               t.category_id, c.name AS category_name, t.created_at,
               s.filename AS source_statement_filename
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN statements s ON s.id = t.source_statement_id
        {where_clause}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
    """

    data_params = [*params, limit, offset]

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(count_sql, params)
            total_row = cur.fetchone()
            total = int(total_row["cnt"]) if total_row else 0

            cur.execute(data_sql, data_params)
            rows = [dict(r) for r in cur.fetchall()]

    return TransactionListPage(items=rows, total=total)
