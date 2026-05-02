"""Setup routes for ledger bootstrap workflows."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pfa.db import connect
from pfa.setup_service import (
    SetupServiceError,
    create_account,
    create_account_alias,
    create_institution,
    list_account_aliases,
    list_accounts,
    list_institutions,
    update_account,
    update_institution,
)

router = APIRouter(tags=["setup"])


def _setup_error(exc: SetupServiceError) -> HTTPException:
    message = str(exc)
    if message.endswith("not found"):
        return HTTPException(status_code=404, detail=message)
    if "already exists" in message:
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=422, detail=message)


class InstitutionBody(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class AccountBody(BaseModel):
    institution_id: UUID
    name: str = Field(min_length=1, max_length=256)
    currency: str = Field(min_length=1, max_length=8)


class AccountOut(BaseModel):
    id: UUID
    institution_id: UUID
    institution_name: str
    name: str
    currency: str


class AccountAliasBody(BaseModel):
    account_id: UUID
    alias: str = Field(min_length=1, max_length=256)


class AccountAliasOut(BaseModel):
    id: UUID
    account_id: UUID
    account_name: str
    alias: str


@router.get("/institutions", response_model=list[InstitutionOut])
def get_institutions():
    with connect() as conn:
        rows = list_institutions(conn)
    return [InstitutionOut(id=row["id"], name=row["name"]) for row in rows]


@router.post("/institutions", response_model=InstitutionOut)
def post_institution(body: InstitutionBody):
    with connect() as conn:
        try:
            institution_id = create_institution(conn, body.name)
        except SetupServiceError as exc:
            raise _setup_error(exc) from exc
    return InstitutionOut(id=institution_id, name=body.name.strip())


@router.put("/institutions/{institution_id}", status_code=204)
def put_institution(institution_id: UUID, body: InstitutionBody):
    with connect() as conn:
        try:
            update_institution(conn, institution_id, body.name)
        except SetupServiceError as exc:
            raise _setup_error(exc) from exc


@router.get("/accounts", response_model=list[AccountOut])
def get_accounts():
    with connect() as conn:
        rows = list_accounts(conn)
    return [AccountOut(**row) for row in rows]


@router.post("/accounts", response_model=AccountOut)
def post_account(body: AccountBody):
    with connect() as conn:
        try:
            account_id = create_account(conn, body.institution_id, body.name, body.currency)
            rows = list_accounts(conn)
        except SetupServiceError as exc:
            raise _setup_error(exc) from exc
    match = next((row for row in rows if row["id"] == account_id), None)
    assert match is not None
    return AccountOut(**match)


@router.put("/accounts/{account_id}", status_code=204)
def put_account(account_id: UUID, body: AccountBody):
    with connect() as conn:
        try:
            update_account(
                conn,
                account_id,
                body.institution_id,
                body.name,
                body.currency,
            )
        except SetupServiceError as exc:
            raise _setup_error(exc) from exc


@router.get("/account-aliases", response_model=list[AccountAliasOut])
def get_account_aliases():
    with connect() as conn:
        rows = list_account_aliases(conn)
    return [AccountAliasOut(**row) for row in rows]


@router.post("/account-aliases", response_model=AccountAliasOut)
def post_account_alias(body: AccountAliasBody):
    with connect() as conn:
        try:
            alias_id = create_account_alias(conn, body.account_id, body.alias)
            rows = list_account_aliases(conn)
        except SetupServiceError as exc:
            raise _setup_error(exc) from exc
    match = next((row for row in rows if row["id"] == alias_id), None)
    assert match is not None
    return AccountAliasOut(**match)
