"""create source_bank and transaction_type enums

Revision ID: 001
Revises: 
Create Date: 2026-04-28 22:01:49.054260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE source_bank AS ENUM ('chase', 'amex', 'capital_one', 'robinhood')")
    op.execute("CREATE TYPE transaction_type AS ENUM ('debit', 'credit')")
    op.execute("CREATE TYPE statement_status AS ENUM ('processing', 'complete', 'failed')")


def downgrade() -> None:
    op.execute("DROP TYPE IF EXISTS statement_status")
    op.execute("DROP TYPE IF EXISTS transaction_type")
    op.execute("DROP TYPE IF EXISTS source_bank")
