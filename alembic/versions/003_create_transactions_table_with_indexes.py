"""create transactions table with indexes

Revision ID: 003
Revises: 002
Create Date: 2026-04-28 22:02:29.073608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, Sequence[str], None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            statement_id UUID NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            description TEXT NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'USD',
            category TEXT,
            merchant TEXT,
            source_bank source_bank NOT NULL,
            transaction_type transaction_type NOT NULL,
            raw_description TEXT NOT NULL,
            raw_description_hash CHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_transactions_date ON transactions (date)")
    op.execute("CREATE INDEX idx_transactions_source_bank ON transactions (source_bank)")
    op.execute("CREATE INDEX idx_transactions_category ON transactions (category)")
    op.execute("CREATE INDEX idx_transactions_merchant ON transactions (merchant)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS transactions")
