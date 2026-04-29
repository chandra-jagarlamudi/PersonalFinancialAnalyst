"""SQLAlchemy async engine and session factory.

Usage:
    from financial_assistant.db import get_session

    async def my_handler():
        async with get_session() as session:
            result = await session.execute(...)
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Pool sizing from environment (defaults tuned for a single-user local server)
_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        from financial_assistant.config import get_settings

        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=_POOL_SIZE,
            max_overflow=_MAX_OVERFLOW,
            pool_timeout=_POOL_TIMEOUT,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
