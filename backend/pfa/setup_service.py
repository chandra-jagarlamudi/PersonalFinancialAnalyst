"""Setup CRUD for institutions, accounts, and account aliases."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row


class SetupServiceError(ValueError):
    pass


def _trim_required(value: str, *, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise SetupServiceError(f"{field_name} is required")
    return trimmed


def list_institutions(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, name, created_at FROM institutions ORDER BY name ASC, created_at ASC"
        )
        return [dict(row) for row in cur.fetchall()]


def create_institution(conn: psycopg.Connection, name: str) -> UUID:
    name = _trim_required(name, field_name="name")
    try:
        row = conn.execute(
            "INSERT INTO institutions (name) VALUES (%s) RETURNING id",
            (name,),
        ).fetchone()
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        raise SetupServiceError("institution already exists") from exc
    conn.commit()
    assert row is not None
    return UUID(str(row[0]))


def update_institution(conn: psycopg.Connection, institution_id: UUID, name: str) -> None:
    name = _trim_required(name, field_name="name")
    try:
        row = conn.execute(
            "UPDATE institutions SET name = %s WHERE id = %s RETURNING id",
            (name, str(institution_id)),
        ).fetchone()
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        raise SetupServiceError("institution already exists") from exc
    if row is None:
        conn.rollback()
        raise SetupServiceError("institution not found")
    conn.commit()


def list_accounts(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.institution_id, i.name AS institution_name, a.name, a.currency, a.created_at
            FROM accounts a
            JOIN institutions i ON i.id = a.institution_id
            ORDER BY i.name ASC, a.name ASC, a.created_at ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def create_account(
    conn: psycopg.Connection, institution_id: UUID, name: str, currency: str
) -> UUID:
    name = _trim_required(name, field_name="name")
    currency = _trim_required(currency, field_name="currency").upper()
    try:
        row = conn.execute(
            """
            INSERT INTO accounts (institution_id, name, currency)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (str(institution_id), name, currency),
        ).fetchone()
    except pg_errors.ForeignKeyViolation as exc:
        conn.rollback()
        raise SetupServiceError("institution not found") from exc
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        raise SetupServiceError("account already exists") from exc
    conn.commit()
    assert row is not None
    return UUID(str(row[0]))


def get_account(conn: psycopg.Connection, account_id: UUID) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.institution_id, i.name AS institution_name, a.name, a.currency
            FROM accounts a
            JOIN institutions i ON i.id = a.institution_id
            WHERE a.id = %s
            LIMIT 1
            """,
            (str(account_id),),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def update_account(
    conn: psycopg.Connection,
    account_id: UUID,
    institution_id: UUID,
    name: str,
    currency: str,
) -> None:
    name = _trim_required(name, field_name="name")
    currency = _trim_required(currency, field_name="currency").upper()
    try:
        row = conn.execute(
            """
            UPDATE accounts
            SET institution_id = %s, name = %s, currency = %s
            WHERE id = %s
            RETURNING id
            """,
            (str(institution_id), name, currency, str(account_id)),
        ).fetchone()
    except pg_errors.ForeignKeyViolation as exc:
        conn.rollback()
        raise SetupServiceError("institution not found") from exc
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        raise SetupServiceError("account already exists") from exc
    if row is None:
        conn.rollback()
        raise SetupServiceError("account not found")
    conn.commit()


def list_account_aliases(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT aa.id, aa.account_id, a.name AS account_name, aa.alias, aa.created_at
            FROM account_aliases aa
            JOIN accounts a ON a.id = aa.account_id
            ORDER BY aa.alias ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def create_account_alias(conn: psycopg.Connection, account_id: UUID, alias: str) -> UUID:
    alias = _trim_required(alias, field_name="alias")
    try:
        row = conn.execute(
            """
            INSERT INTO account_aliases (account_id, alias)
            VALUES (%s, %s)
            RETURNING id
            """,
            (str(account_id), alias),
        ).fetchone()
    except pg_errors.ForeignKeyViolation as exc:
        conn.rollback()
        raise SetupServiceError("account not found") from exc
    except pg_errors.UniqueViolation as exc:
        conn.rollback()
        raise SetupServiceError("account alias already exists") from exc
    conn.commit()
    assert row is not None
    return UUID(str(row[0]))


def get_account_alias(conn: psycopg.Connection, alias_id: UUID) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT aa.id, aa.account_id, a.name AS account_name, aa.alias
            FROM account_aliases aa
            JOIN accounts a ON a.id = aa.account_id
            WHERE aa.id = %s
            LIMIT 1
            """,
            (str(alias_id),),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None
