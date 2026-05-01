"""HTTP routes for categorization rules, manual corrections, and rule proposals (slice 7)."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pfa.categorization import apply_rules_retroactively
from pfa.db import connect

router = APIRouter(tags=["categorization"])


class RuleCreate(BaseModel):
    category_id: UUID
    pattern: str = Field(min_length=1)
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


class RuleProposalIn(BaseModel):
    pattern: str = Field(min_length=1)
    apply_retroactively: bool = False


class RuleProposalOut(BaseModel):
    proposed_rule: dict
    would_affect_count: int


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
    try:
        re.compile(body.pattern)
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"invalid regex: {exc}") from exc

    with connect() as conn:
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


@router.post("/transactions/{transaction_id}/rule-proposal", response_model=RuleProposalOut)
def propose_rule(transaction_id: UUID, body: RuleProposalIn):
    try:
        re.compile(body.pattern)
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"invalid regex: {exc}") from exc

    with connect() as conn:
        tx = conn.execute(
            "SELECT id FROM transactions WHERE id = %s", (str(transaction_id),)
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")

        count_row = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL AND description_normalized ~* %s",
            (body.pattern,),
        ).fetchone()
        would_affect = count_row[0] if count_row else 0

    return RuleProposalOut(
        proposed_rule={"pattern": body.pattern, "apply_retroactively": body.apply_retroactively},
        would_affect_count=would_affect,
    )
