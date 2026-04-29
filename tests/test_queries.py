"""T-029, T-030 — query interface and session tests."""

import asyncio
import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from financial_assistant.models import (
    SourceBank,
    Statement,
    StatementStatus,
    Transaction,
    TransactionType,
    UserSession,
)
from financial_assistant.queries import (
    get_monthly_totals,
    get_statement_by_hash,
    get_transactions,
    get_transactions_by_merchant,
    insert_statement_and_transactions,
    insert_transactions,
)


def _make_tx(
    stmt_id: uuid.UUID,
    tx_date: date,
    amount: Decimal,
    raw_desc: str,
    bank: SourceBank = SourceBank.chase,
    tx_type: TransactionType = TransactionType.debit,
    category: str | None = None,
    merchant: str | None = None,
) -> Transaction:
    t = Transaction()
    t.id = uuid.uuid4()
    t.statement_id = stmt_id
    t.date = tx_date
    t.description = raw_desc[:100]
    t.amount = amount
    t.source_bank = bank
    t.transaction_type = tx_type
    t.raw_description = raw_desc
    t.raw_description_hash = hashlib.sha256(raw_desc.encode()).hexdigest()
    t.category = category
    t.merchant = merchant
    return t


def _make_stmt(file_hash: str | None = None) -> Statement:
    s = Statement()
    s.id = uuid.uuid4()
    s.filename = "test.csv"
    s.source_bank = SourceBank.chase
    s.file_hash = file_hash or uuid.uuid4().hex
    s.period_start = date(2024, 1, 1)
    s.period_end = date(2024, 1, 31)
    s.transaction_count = 0
    s.status = StatementStatus.complete
    return s


# ── T-030: session schema ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_insert_and_query_unexpired(engine):
    """T-030: insert session, valid id + unexpired → returns row."""
    from sqlalchemy import text

    factory = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=30)
    session_id = uuid.uuid4()

    async with factory() as s:
        await s.execute(
            text(
                "INSERT INTO sessions (id, user_email, created_at, expires_at) "
                "VALUES (:id, :email, :ca, :ea)"
            ),
            {"id": str(session_id), "email": "test@test.com", "ca": now, "ea": expires_at},
        )
        await s.commit()

    async with factory() as s:
        result = await s.execute(
            text("SELECT id, user_email FROM sessions WHERE id = :id AND expires_at > now()"),
            {"id": str(session_id)},
        )
        row = result.fetchone()
        assert row is not None, "Expected row for valid unexpired session"
        assert row.user_email == "test@test.com"

    # Cleanup
    async with factory() as s:
        await s.execute(text("DELETE FROM sessions WHERE id = :id"), {"id": str(session_id)})
        await s.commit()


@pytest.mark.asyncio
async def test_session_expired_returns_no_rows(engine):
    """T-030: expired session id returns no rows."""
    from sqlalchemy import text

    factory = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    expired_at = now - timedelta(days=1)  # already expired
    session_id = uuid.uuid4()

    async with factory() as s:
        await s.execute(
            text(
                "INSERT INTO sessions (id, user_email, created_at, expires_at) "
                "VALUES (:id, :email, :ca, :ea)"
            ),
            {"id": str(session_id), "email": "test@test.com", "ca": now, "ea": expired_at},
        )
        await s.commit()

    async with factory() as s:
        result = await s.execute(
            text("SELECT id FROM sessions WHERE id = :id AND expires_at > now()"),
            {"id": str(session_id)},
        )
        assert result.fetchone() is None, "Expired session should return no rows"

    # Cleanup
    async with factory() as s:
        await s.execute(text("DELETE FROM sessions WHERE id = :id"), {"id": str(session_id)})
        await s.commit()


@pytest.mark.asyncio
async def test_session_unknown_id_returns_no_rows(engine):
    """T-030: unknown session id returns no rows."""
    from sqlalchemy import text

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        result = await s.execute(
            text("SELECT id FROM sessions WHERE id = :id AND expires_at > now()"),
            {"id": str(uuid.uuid4())},
        )
        assert result.fetchone() is None


# ── T-029: typed query tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insert_statement_and_transactions_basic(engine):
    """T-029: basic insert_statement_and_transactions returns (attempted, inserted)."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    stmt = _make_stmt()
    txs = [
        _make_tx(stmt.id, date(2024, 1, 15), Decimal("50.00"), f"Purchase {i}")
        for i in range(5)
    ]

    async with factory() as s:
        result = await insert_statement_and_transactions(s, stmt, txs)

    assert result is not None, "Should return counts, not None"
    attempted, inserted = result
    assert attempted == 5
    assert inserted == 5

    # Cleanup
    from sqlalchemy import text
    async with factory() as s:
        await s.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt.id)})
        await s.commit()


@pytest.mark.asyncio
async def test_insert_statement_duplicate_file_hash_returns_none(engine):
    """T-029: duplicate file_hash → returns None."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    file_hash = f"dup_{uuid.uuid4().hex}"
    stmt1 = _make_stmt(file_hash)
    stmt2 = _make_stmt(file_hash)

    async with factory() as s:
        r1 = await insert_statement_and_transactions(s, stmt1, [])
    assert r1 is not None, "First insert should succeed"

    async with factory() as s:
        r2 = await insert_statement_and_transactions(s, stmt2, [])
    assert r2 is None, "Second insert with same file_hash should return None"

    # Cleanup
    from sqlalchemy import text
    async with factory() as s:
        await s.execute(text("DELETE FROM statements WHERE file_hash = :fh"), {"fh": file_hash})
        await s.commit()


@pytest.mark.asyncio
async def test_concurrent_insert_same_file_hash(engine):
    """T-029: concurrent insert_statement_and_transactions with same file_hash → one counts, one None."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    file_hash = f"concurrent_{uuid.uuid4().hex}"
    results: list = []

    async def do_insert():
        s = _make_stmt(file_hash)
        async with factory() as session:
            r = await insert_statement_and_transactions(session, s, [])
            results.append(r)

    await asyncio.gather(do_insert(), do_insert())

    nones = [r for r in results if r is None]
    counts = [r for r in results if r is not None]
    assert len(nones) == 1, f"Expected 1 None, got results: {results}"
    assert len(counts) == 1, f"Expected 1 count tuple, got results: {results}"

    # Cleanup
    from sqlalchemy import text
    async with factory() as s:
        await s.execute(text("DELETE FROM statements WHERE file_hash = :fh"), {"fh": file_hash})
        await s.commit()


@pytest.mark.asyncio
async def test_insert_transactions_dedup_on_conflict(session: AsyncSession):
    """T-029: insert same transaction twice → only one row stored."""
    stmt = _make_stmt()
    session.add(stmt)
    await session.flush()

    tx = _make_tx(stmt.id, date(2024, 1, 15), Decimal("50.00"), "Duplicate tx")
    attempted, inserted = await insert_transactions(session, stmt.id, [tx, tx])

    assert attempted == 2
    assert inserted == 1, f"Expected 1 inserted (dedup), got {inserted}"

    # Cleanup
    from sqlalchemy import text
    await session.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt.id)})
    await session.commit()


@pytest.mark.asyncio
async def test_get_transactions_date_filter(session: AsyncSession):
    """T-029: get_transactions returns correct rows for date range."""
    stmt = _make_stmt()
    session.add(stmt)
    await session.flush()

    txs = [
        _make_tx(stmt.id, date(2024, 1, 10), Decimal("10.00"), f"Jan tx {i}")
        for i in range(3)
    ] + [
        _make_tx(stmt.id, date(2024, 2, 10), Decimal("20.00"), f"Feb tx {i}")
        for i in range(2)
    ]
    await insert_transactions(session, stmt.id, txs)
    await session.flush()

    jan_txs = await get_transactions(
        session, date(2024, 1, 1), date(2024, 1, 31)
    )
    assert len(jan_txs) == 3, f"Expected 3 Jan txns, got {len(jan_txs)}"

    # Cleanup
    from sqlalchemy import text
    await session.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt.id)})
    await session.commit()


@pytest.mark.asyncio
async def test_get_transactions_invalid_dates(session: AsyncSession):
    """T-029: start_date > end_date raises ValueError."""
    with pytest.raises(ValueError, match="start_date"):
        await get_transactions(session, date(2024, 2, 1), date(2024, 1, 1))


@pytest.mark.asyncio
async def test_get_monthly_totals(session: AsyncSession):
    """T-029: get_monthly_totals returns dict[category, Decimal]."""
    stmt = _make_stmt()
    session.add(stmt)
    await session.flush()

    txs = [
        _make_tx(stmt.id, date(2024, 3, 5), Decimal("100.00"), "Groceries A", category="groceries"),
        _make_tx(stmt.id, date(2024, 3, 10), Decimal("50.00"), "Groceries B", category="groceries"),
        _make_tx(stmt.id, date(2024, 3, 15), Decimal("200.00"), "Rent March", category="housing"),
    ]
    await insert_transactions(session, stmt.id, txs)
    await session.flush()

    totals = await get_monthly_totals(session, 2024, 3)
    assert "groceries" in totals
    assert totals["groceries"] == Decimal("150.00"), f"Got {totals['groceries']}"
    assert "housing" in totals

    # Cleanup
    from sqlalchemy import text
    await session.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt.id)})
    await session.commit()


@pytest.mark.asyncio
async def test_get_monthly_totals_invalid_month(session: AsyncSession):
    """T-029: invalid month raises ValueError."""
    with pytest.raises(ValueError, match="month"):
        await get_monthly_totals(session, 2024, 13)


@pytest.mark.asyncio
async def test_get_statement_by_hash(session: AsyncSession):
    """T-029: get_statement_by_hash returns statement or None."""
    stmt = _make_stmt()
    session.add(stmt)
    await session.commit()

    found = await get_statement_by_hash(session, stmt.file_hash)
    assert found is not None
    assert found.file_hash == stmt.file_hash

    missing = await get_statement_by_hash(session, "nonexistent_hash")
    assert missing is None

    # Cleanup
    from sqlalchemy import text
    await session.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt.id)})
    await session.commit()


@pytest.mark.asyncio
async def test_get_statement_by_hash_empty_raises(session: AsyncSession):
    """T-029: empty file_hash raises ValueError."""
    with pytest.raises(ValueError, match="file_hash"):
        await get_statement_by_hash(session, "")


@pytest.mark.asyncio
async def test_get_transactions_by_merchant(session: AsyncSession):
    """T-029: get_transactions_by_merchant returns matching rows."""
    stmt = _make_stmt()
    session.add(stmt)
    await session.flush()

    txs = [
        _make_tx(stmt.id, date(2024, 1, 5), Decimal("15.49"), "Netflix monthly", merchant="netflix"),
        _make_tx(stmt.id, date(2024, 1, 10), Decimal("50.00"), "Amazon Prime", merchant="amazon"),
    ]
    await insert_transactions(session, stmt.id, txs)
    await session.flush()

    netflix = await get_transactions_by_merchant(session, "netflix", date(2024, 1, 1), date(2024, 1, 31))
    assert len(netflix) == 1
    assert netflix[0].merchant == "netflix"

    # Cleanup
    from sqlalchemy import text
    await session.execute(text("DELETE FROM statements WHERE id = :id"), {"id": str(stmt.id)})
    await session.commit()
