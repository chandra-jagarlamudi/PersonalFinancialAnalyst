"""Typed query functions for the analytics and ingestion domains.

All functions accept an AsyncSession and return typed results.
Raise ValueError on invalid inputs (e.g., missing required fields).
"""

import hashlib
import datetime as _dt
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from financial_assistant.models import (
    SourceBank,
    Statement,
    StatementStatus,
    Transaction,
    TransactionType,
    UserSession,
)


# ── Read queries ─────────────────────────────────────────────────────────────


async def get_transactions(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    bank: Optional[SourceBank] = None,
    category: Optional[str] = None,
) -> list[Transaction]:
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} must be <= end_date {end_date}")

    stmt = select(Transaction).where(
        and_(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
    )
    if bank is not None:
        stmt = stmt.where(Transaction.source_bank == bank)
    if category is not None:
        stmt = stmt.where(Transaction.category == category)

    result = await session.execute(stmt.order_by(Transaction.date.desc()))
    return list(result.scalars().all())


async def get_transactions_by_merchant(
    session: AsyncSession,
    merchant: str,
    start_date: date,
    end_date: date,
) -> list[Transaction]:
    if not merchant or not merchant.strip():
        raise ValueError("merchant must not be empty")
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} must be <= end_date {end_date}")

    stmt = (
        select(Transaction)
        .where(
            and_(
                func.lower(Transaction.merchant) == merchant.lower().strip(),
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
        )
        .order_by(Transaction.date.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_monthly_totals(
    session: AsyncSession,
    year: int,
    month: int,
) -> dict[str, Decimal]:
    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1-12, got {month}")
    if year < 1900 or year > 2100:
        raise ValueError(f"year out of range: {year}")

    start = date(year, month, 1)
    # last day of month
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    stmt = (
        select(Transaction.category, func.sum(Transaction.amount).label("total"))
        .where(
            and_(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.transaction_type == TransactionType.debit,
            )
        )
        .group_by(Transaction.category)
    )
    result = await session.execute(stmt)
    return {
        (row.category or "uncategorized"): Decimal(str(row.total))
        for row in result
    }


async def get_statement_by_hash(
    session: AsyncSession,
    file_hash: str,
) -> Optional[Statement]:
    if not file_hash or not file_hash.strip():
        raise ValueError("file_hash must not be empty")

    stmt = select(Statement).where(Statement.file_hash == file_hash)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ── Write queries ─────────────────────────────────────────────────────────────


async def insert_transactions(
    session: AsyncSession,
    statement_id,
    transactions: list[Transaction],
) -> tuple[int, int]:
    """Insert transactions with ON CONFLICT DO NOTHING dedup.

    Returns (attempted, inserted). inserted = attempted - duplicates_skipped.
    """
    if not transactions:
        return (0, 0)

    attempted = len(transactions)

    # Count rows before insert for accurate inserted count
    pre_count_result = await session.execute(
        select(func.count()).where(Transaction.statement_id == statement_id)
    )
    pre_count = pre_count_result.scalar() or 0

    import uuid as _uuid

    rows = [
        {
            "id": str(tx.id) if tx.id else str(_uuid.uuid4()),
            "statement_id": str(statement_id),
            "date": tx.date,
            "description": tx.description,
            "amount": tx.amount,
            "currency": tx.currency or "USD",
            "category": tx.category,
            "merchant": tx.merchant,
            "source_bank": tx.source_bank.value if isinstance(tx.source_bank, SourceBank) else tx.source_bank,
            "transaction_type": tx.transaction_type.value if isinstance(tx.transaction_type, TransactionType) else tx.transaction_type,
            "raw_description": tx.raw_description,
            "raw_description_hash": tx.raw_description_hash,
            "created_at": _dt.datetime.now(_dt.timezone.utc),
        }
        for tx in transactions
    ]

    stmt = pg_insert(Transaction).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_transaction_dedup"
    )
    await session.execute(stmt)
    await session.flush()

    post_count_result = await session.execute(
        select(func.count()).where(Transaction.statement_id == statement_id)
    )
    post_count = post_count_result.scalar() or 0

    inserted = post_count - pre_count
    return (attempted, inserted)


async def insert_statement_and_transactions(
    session: AsyncSession,
    statement: Statement,
    transactions: list[Transaction],
) -> tuple[int, int] | None:
    """Atomically insert statement (keyed on file_hash) + transactions.

    Returns None if file_hash already exists (caller should 409).
    Returns (attempted, inserted) on success.
    Entire operation is a single DB transaction.
    """
    try:
        # Use INSERT ... ON CONFLICT DO NOTHING and check if row was actually inserted
        import uuid as _uuid2

        insert_stmt = (
            pg_insert(Statement)
            .values(
                id=str(statement.id) if statement.id else str(_uuid2.uuid4()),
                filename=statement.filename,
                source_bank=statement.source_bank.value if isinstance(statement.source_bank, SourceBank) else statement.source_bank,
                file_hash=statement.file_hash,
                period_start=statement.period_start,
                period_end=statement.period_end,
                transaction_count=0,
                ingested_at=_dt.datetime.now(_dt.timezone.utc),
                status=StatementStatus.processing.value,
            )
            .on_conflict_do_nothing(constraint="statements_file_hash_unique")
            .returning(Statement.id)
        )
        result = await session.execute(insert_stmt)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is None:
            # file_hash already existed — duplicate upload
            return None

        statement_id = inserted_id
        counts = await insert_transactions(session, statement_id, transactions)

        # Update statement with final counts and status
        await session.execute(
            text(
                "UPDATE statements SET transaction_count = :count, status = 'complete' WHERE id = :id"
            ),
            {"count": counts[1], "id": str(statement_id)},
        )

        await session.commit()
        return counts

    except IntegrityError:
        await session.rollback()
        return None
