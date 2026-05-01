"""HTTP routes for categories and envelope budgets (slice 6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from pfa.budget_service import (
    BudgetServiceError,
    budget_status,
    create_category,
    list_budgets,
    list_categories,
    parse_year_month,
    suggest_budget_amounts,
    upsert_budgets,
)
from pfa.db import connect

router = APIRouter(tags=["budgets"])


def _svc_err(exc: BudgetServiceError) -> HTTPException:
    msg = str(exc)
    if "already exists" in msg:
        return HTTPException(status_code=409, detail=msg)
    if "unknown category" in msg:
        return HTTPException(status_code=404, detail=msg)
    return HTTPException(status_code=422, detail=msg)


class CategoryCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str


class BudgetLineIn(BaseModel):
    category_id: UUID
    amount: Annotated[Decimal, Field(ge=0)]


class BudgetPut(BaseModel):
    items: list[BudgetLineIn] = Field(default_factory=list)


class BudgetRowOut(BaseModel):
    category_id: UUID
    slug: str
    name: str
    amount: Decimal
    currency: str


class BudgetStatusOut(BaseModel):
    category_id: UUID
    slug: str
    name: str
    budget_amount: Decimal
    spent_mtd: Decimal
    projected_spend: Decimal
    remaining_mtd: Decimal
    remaining_projected: Decimal
    days_elapsed: int
    days_in_month: int


class SuggestBody(BaseModel):
    lookback_months: Annotated[int, Field(ge=1, le=120)] = 6


class SuggestionOut(BaseModel):
    category_id: UUID
    slug: str
    name: str
    suggested_amount: Decimal
    history_total_spend: Decimal
    lookback_months: int


@router.post("/categories", response_model=CategoryOut)
def post_category(body: CategoryCreate):
    with connect() as conn:
        try:
            cid = create_category(conn, body.slug, body.name)
        except BudgetServiceError as e:
            raise _svc_err(e) from e
    slug = body.slug.strip()
    return CategoryOut(id=cid, slug=slug, name=body.name.strip())


@router.get("/categories", response_model=list[CategoryOut])
def get_categories():
    with connect() as conn:
        rows = list_categories(conn)
    return [
        CategoryOut(id=r["id"], slug=r["slug"], name=r["name"]) for r in rows
    ]


@router.put("/budgets/{year_month}")
def put_budgets(year_month: str, body: BudgetPut):
    try:
        ms = parse_year_month(year_month)
    except BudgetServiceError as e:
        raise _svc_err(e) from e
    tuples = [(it.category_id, it.amount) for it in body.items]
    with connect() as conn:
        try:
            upsert_budgets(conn, ms, tuples)
        except BudgetServiceError as e:
            raise _svc_err(e) from e
    return Response(status_code=204)


@router.get("/budgets/{year_month}", response_model=list[BudgetRowOut])
def get_budgets(year_month: str):
    try:
        ms = parse_year_month(year_month)
    except BudgetServiceError as e:
        raise _svc_err(e) from e
    with connect() as conn:
        rows = list_budgets(conn, ms)
    return [
        BudgetRowOut(
            category_id=r["category_id"],
            slug=r["slug"],
            name=r["name"],
            amount=r["amount"],
            currency=r["currency"],
        )
        for r in rows
    ]


@router.get("/budgets/{year_month}/status", response_model=list[BudgetStatusOut])
def get_budget_status(
    year_month: str,
    as_of: Annotated[
        date | None,
        Query(description="Anchor date for MTD and projection (default: today)"),
    ] = None,
):
    try:
        ms = parse_year_month(year_month)
    except BudgetServiceError as e:
        raise _svc_err(e) from e
    anchor = as_of or date.today()
    with connect() as conn:
        rows = budget_status(conn, ms, anchor)
    return [BudgetStatusOut(**r) for r in rows]


@router.post("/budgets/{year_month}/suggest", response_model=list[SuggestionOut])
def post_suggest(
    year_month: str,
    body: Annotated[SuggestBody | None, Body()] = None,
):
    try:
        ms = parse_year_month(year_month)
    except BudgetServiceError as e:
        raise _svc_err(e) from e
    lookback = body.lookback_months if body is not None else 6
    with connect() as conn:
        rows = suggest_budget_amounts(conn, ms, lookback)
    return [SuggestionOut(**r) for r in rows]
