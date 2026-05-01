"""Postgres connection and schema bootstrap."""

from __future__ import annotations

import os
from importlib import resources

import psycopg


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def load_schema_sql() -> str:
    return resources.files("pfa").joinpath("schema.sql").read_text(encoding="utf-8")


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_schema_sql())
    conn.commit()


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url())
