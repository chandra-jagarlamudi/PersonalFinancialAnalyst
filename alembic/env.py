"""Alembic migration environment.

Reads DATABASE_URL from environment. Converts asyncpg URL to psycopg2 for
synchronous migration execution (Alembic uses sync connections).
"""

import os
import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # Convert asyncpg driver to psycopg2 for sync migrations
    url = re.sub(r"postgresql\+asyncpg://", "postgresql+psycopg2://", url)
    return url


target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = alembic_config.get_section(alembic_config.config_ini_section, {})
    section["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
