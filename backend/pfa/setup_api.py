"""Institution, account, and account-alias HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from pfa.db import connect

router = APIRouter(tags=["setup"])


class InstitutionIn(BaseModel):
    name: str


class InstitutionOut(BaseModel):
    id: UUID
    name: str


class AccountIn(BaseModel):
    institution_id: UUID
    name: str
    currency: str = "USD"


class AccountOut(BaseModel):
    id: UUID
    institution_id: UUID
    name: str
    currency: str


@router.post("/institutions", response_model=InstitutionOut)
def create_institution(body: InstitutionIn):
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO institutions (name) VALUES (%s) RETURNING id, name",
            (body.name,),
        ).fetchone()
        conn.commit()
    assert row is not None
    return InstitutionOut(id=row[0], name=row[1])


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions():
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name FROM institutions ORDER BY name")
            return [InstitutionOut(**row) for row in cur.fetchall()]


@router.post("/accounts", response_model=AccountOut)
def create_account(body: AccountIn):
    with connect() as conn:
        inst = conn.execute(
            "SELECT 1 FROM institutions WHERE id = %s",
            (str(body.institution_id),),
        ).fetchone()
        if inst is None:
            raise HTTPException(status_code=404, detail="institution not found")
        row = conn.execute(
            """
            INSERT INTO accounts (institution_id, name, currency)
            VALUES (%s, %s, %s)
            RETURNING id, institution_id, name, currency
            """,
            (str(body.institution_id), body.name, body.currency),
        ).fetchone()
        conn.commit()
    assert row is not None
    return AccountOut(id=row[0], institution_id=row[1], name=row[2], currency=row[3])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts():
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, institution_id, name, currency FROM accounts ORDER BY name"
            )
            return [AccountOut(**row) for row in cur.fetchall()]
