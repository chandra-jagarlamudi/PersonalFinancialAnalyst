"""create statements table

Revision ID: 002
Revises: 001
Create Date: 2026-04-28 22:02:14.194528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, Sequence[str], None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE statements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            filename TEXT NOT NULL,
            source_bank source_bank NOT NULL,
            file_hash TEXT NOT NULL,
            period_start DATE,
            period_end DATE,
            transaction_count INTEGER NOT NULL DEFAULT 0,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status statement_status NOT NULL DEFAULT 'processing',
            error_message TEXT,
            CONSTRAINT statements_file_hash_unique UNIQUE (file_hash)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS statements")
