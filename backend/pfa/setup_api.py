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


class AccountTypeOut(BaseModel):
    id: UUID
    code: str
    label: str
    sort_order: int


class AccountIn(BaseModel):
    institution_id: UUID
    account_type_id: UUID
    name: str
    currency: str = "USD"


class AccountOut(BaseModel):
    id: UUID
    institution_id: UUID
    account_type_id: UUID
    account_type_label: str
    name: str
    currency: str


@router.get("/account-types", response_model=list[AccountTypeOut])
def list_account_types():
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, code, label, sort_order
                FROM account_types
                ORDER BY sort_order, label
                """
            )
            return [AccountTypeOut(**row) for row in cur.fetchall()]


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
        type_ok = conn.execute(
            "SELECT 1 FROM account_types WHERE id = %s",
            (str(body.account_type_id),),
        ).fetchone()
        if type_ok is None:
            raise HTTPException(status_code=404, detail="account type not found")
        row = conn.execute(
            """
            INSERT INTO accounts (institution_id, account_type_id, name, currency)
            VALUES (%s, %s, %s, %s)
            RETURNING id, institution_id, account_type_id, name, currency
            """,
            (
                str(body.institution_id),
                str(body.account_type_id),
                body.name,
                body.currency,
            ),
        ).fetchone()
        assert row is not None
        lab = conn.execute(
            "SELECT label FROM account_types WHERE id = %s",
            (str(row[2]),),
        ).fetchone()
        assert lab is not None
        conn.commit()
    return AccountOut(
        id=row[0],
        institution_id=row[1],
        account_type_id=row[2],
        account_type_label=lab[0],
        name=row[3],
        currency=row[4],
    )


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts():
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.institution_id, a.account_type_id, t.label AS account_type_label,
                       a.name, a.currency
                FROM accounts a
                JOIN account_types t ON t.id = a.account_type_id
                ORDER BY a.name
                """
            )
            return [AccountOut(**row) for row in cur.fetchall()]
