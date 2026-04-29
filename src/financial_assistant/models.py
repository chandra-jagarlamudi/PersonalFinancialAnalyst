"""SQLAlchemy ORM models for Transaction, Statement, and Session."""

import enum
import uuid
import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourceBank(str, enum.Enum):
    chase = "chase"
    amex = "amex"
    capital_one = "capital_one"
    robinhood = "robinhood"


class TransactionType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class StatementStatus(str, enum.Enum):
    processing = "processing"
    complete = "complete"
    failed = "failed"


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    source_bank: Mapped[SourceBank] = mapped_column(
        Enum(SourceBank, name="source_bank", create_type=False), nullable=False
    )
    file_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    period_start: Mapped[dt.date | None] = mapped_column(nullable=True)
    period_end: Mapped[dt.date | None] = mapped_column(nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.timezone.utc),
    )
    status: Mapped[StatementStatus] = mapped_column(
        Enum(StatementStatus, name="statement_status", create_type=False),
        nullable=False,
        default=StatementStatus.processing,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="statement", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[dt.date] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_bank: Mapped[SourceBank] = mapped_column(
        Enum(SourceBank, name="source_bank", create_type=False), nullable=False
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", create_type=False), nullable=False
    )
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_description_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.timezone.utc),
    )

    statement: Mapped["Statement"] = relationship("Statement", back_populates="transactions")

    __table_args__ = (
        UniqueConstraint(
            "source_bank", "date", "amount", "raw_description_hash",
            name="uq_transaction_dedup",
        ),
        Index("idx_transactions_date", "date"),
        Index("idx_transactions_source_bank", "source_bank"),
        Index("idx_transactions_category", "category"),
        Index("idx_transactions_merchant", "merchant"),
    )


class UserSession(Base):
    """Server-side auth session (table name: sessions)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.timezone.utc),
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_sessions_expires_at", "expires_at"),)
