"""Shared pytest fixtures."""

from __future__ import annotations

import os
import time
import uuid

import psycopg
import pytest


@pytest.fixture(autouse=True)
def clear_langchain_tracing_env(monkeypatch):
    """Keep chat/tool tests deterministic vs developer LANGCHAIN_TRACING_V2; tests that need tracing opt in."""
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("PFA_AUTH_USERNAME", "admin")
    monkeypatch.setenv("PFA_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("PFA_SESSION_COOKIE_SECURE", "false")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("DATABASE_URL"):
        return
    skip_int = pytest.mark.skip(reason="set DATABASE_URL to run integration tests")
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(skip_int)


@pytest.fixture
def database_url():
    return os.environ["DATABASE_URL"]


@pytest.fixture
def db_conn(database_url):
    deadline = time.time() + 45
    last_exc: BaseException | None = None
    conn = None
    while time.time() < deadline:
        try:
            conn = psycopg.connect(database_url, connect_timeout=5)
            break
        except Exception as e:
            last_exc = e
            time.sleep(0.5)
    else:
        raise RuntimeError(f"could not connect to Postgres: {last_exc}") from last_exc

    from pfa.db import ensure_schema

    ensure_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def clean_db(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "TRUNCATE auth_sessions, budgets, transactions, statements, accounts, institutions, categories RESTART IDENTITY CASCADE"
        )
    db_conn.commit()
    yield db_conn


@pytest.fixture
def sample_account_id(clean_db):
    iid = uuid.uuid4()
    aid = uuid.uuid4()
    with clean_db.cursor() as cur:
        cur.execute(
            "INSERT INTO institutions (id, name) VALUES (%s, %s)",
            (str(iid), "Test Bank"),
        )
        cur.execute(
            """
            INSERT INTO accounts (id, institution_id, name, currency)
            VALUES (%s, %s, %s, %s)
            """,
            (str(aid), str(iid), "Checking", "USD"),
        )
    clean_db.commit()
    return aid


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(d))
    return d


@pytest.fixture
def client(database_url, monkeypatch, clean_db):
    monkeypatch.setenv("DATABASE_URL", database_url)
    from fastapi.testclient import TestClient
    from pfa.main import app

    # Context manager runs lifespan startup (schema DDL) before requests.
    with TestClient(app) as test_client:
        login = test_client.post(
            "/auth/login",
            json={"username": "admin", "password": "test-password"},
        )
        assert login.status_code == 200
        yield test_client


@pytest.fixture
def anon_client(database_url, monkeypatch, clean_db):
    monkeypatch.setenv("DATABASE_URL", database_url)
    from fastapi.testclient import TestClient
    from pfa.main import app

    with TestClient(app) as test_client:
        yield test_client
