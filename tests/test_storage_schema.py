"""T-019, T-020, T-021, T-022 — storage schema tests.

Requires live Postgres at TEST_DATABASE_URL (default: localhost:5433/financial_assistant_test).
"""

import asyncio
import hashlib
import subprocess
import time
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/financial_assistant_test"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


async def _insert_statement(session: AsyncSession, file_hash: str | None = None) -> uuid.UUID:
    fh = file_hash or str(uuid.uuid4())
    stmt_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO statements (id, filename, source_bank, file_hash,
                period_start, period_end, transaction_count, status)
            VALUES (:id, :fn, 'chase'::source_bank, :fh,
                    '2024-01-01', '2024-01-31', 0, 'complete'::statement_status)
            """
        ),
        {"id": str(stmt_id), "fn": "test.csv", "fh": fh},
    )
    await session.commit()
    return stmt_id


# ── T-021: migration idempotency ─────────────────────────────────────────────


def test_migrate_up_idempotent():
    """T-021: alembic upgrade head on already-migrated DB is a no-op."""
    import os

    env = {**os.environ, "DATABASE_URL": TEST_DB_URL}
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "Running upgrade" not in result.stderr, f"Unexpected migration: {result.stderr}"


@pytest.mark.asyncio
async def test_migrate_schema_tables_exist(engine):
    """T-021: all required tables exist after migrate up."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )
        names = {r[0] for r in result}
    assert "statements" in names
    assert "transactions" in names
    assert "sessions" in names


# ── T-019: date-range query performance ──────────────────────────────────────


@pytest.mark.asyncio
async def test_date_range_query_under_100ms(session: AsyncSession):
    """T-019: insert 1000 transactions, date-range query returns correct subset <100ms."""
    stmt_id = await _insert_statement(session)

    for i in range(1000):
        tx_date = date(2024, 1, 1) + timedelta(days=i % 90)
        await session.execute(
            text(
                """
                INSERT INTO transactions
                  (statement_id, date, description, amount, source_bank,
                   transaction_type, raw_description, raw_description_hash)
                VALUES (:sid, :dt, :desc, :amt,
                        'chase'::source_bank, 'debit'::transaction_type, :raw, :hash)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "sid": str(stmt_id),
                "dt": tx_date,
                "desc": f"tx {i}",
                "amt": "10.00",
                "raw": f"raw tx {i}",
                "hash": _hash(f"raw tx {i}"),
            },
        )
    await session.commit()

    start = time.monotonic()
    result = await session.execute(
        text(
            "SELECT id FROM transactions WHERE statement_id = :sid"
            " AND date >= '2024-01-01' AND date < '2024-02-01'"
        ),
        {"sid": str(stmt_id)},
    )
    rows = result.fetchall()
    elapsed_ms = (time.monotonic() - start) * 1000

    assert len(rows) > 0
    assert elapsed_ms < 100, f"Date-range query took {elapsed_ms:.1f}ms (limit: 100ms)"

    # Cleanup
    await session.execute(
        text("DELETE FROM transactions WHERE statement_id = :sid"), {"sid": str(stmt_id)}
    )
    await session.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt_id)})
    await session.commit()


# ── T-020: concurrent file_hash unique constraint ─────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_file_hash_unique(engine):
    """T-020: two parallel inserts with same file_hash → exactly one succeeds."""
    from sqlalchemy.exc import IntegrityError

    factory = async_sessionmaker(engine, expire_on_commit=False)
    file_hash = f"conflict_{uuid.uuid4().hex}"
    results: list[str] = []

    async def try_insert() -> None:
        async with factory() as s:
            try:
                await s.execute(
                    text(
                        """
                        INSERT INTO statements (id, filename, source_bank, file_hash,
                            period_start, period_end, transaction_count, status)
                        VALUES (:id, 'same.csv', 'amex'::source_bank, :fh,
                                '2024-01-01', '2024-01-31', 0, 'complete'::statement_status)
                        """
                    ),
                    {"id": str(uuid.uuid4()), "fh": file_hash},
                )
                await s.commit()
                results.append("ok")
            except IntegrityError:
                await s.rollback()
                results.append("conflict")

    await asyncio.gather(try_insert(), try_insert())

    assert results.count("ok") == 1, f"Expected exactly 1 success, got: {results}"
    assert results.count("conflict") == 1, f"Expected exactly 1 conflict, got: {results}"

    async with factory() as s:
        count = await s.execute(
            text("SELECT COUNT(*) FROM statements WHERE file_hash = :fh"), {"fh": file_hash}
        )
        assert count.scalar() == 1
        await s.execute(text("DELETE FROM statements WHERE file_hash = :fh"), {"fh": file_hash})
        await s.commit()


# ── T-022: connection pool under 50 concurrent requests ──────────────────────


@pytest.mark.asyncio
async def test_pool_50_concurrent(engine):
    """T-022: 50 concurrent lightweight queries complete without exhaustion."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    errors: list[str] = []

    async def query_once() -> None:
        try:
            async with factory() as s:
                await s.execute(text("SELECT 1"))
        except Exception as e:
            errors.append(str(e))

    start = time.monotonic()
    await asyncio.gather(*[query_once() for _ in range(50)])
    elapsed_ms = (time.monotonic() - start) * 1000

    assert not errors, f"Pool errors: {errors[:3]}"
    assert elapsed_ms < 10000, f"50 concurrent queries took {elapsed_ms:.0f}ms"
