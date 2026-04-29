"""Shared pytest fixtures for database integration tests."""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set required env vars before any module imports trigger pydantic-settings validation.
# These are test-only placeholders; real values live in .env for the running app.
_TEST_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5433/financial_assistant_test",
    "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "ALLOWED_USER_EMAIL": "test@example.com",
    "LANGSMITH_API_KEY": "ls__test-key",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
    "MCP_API_KEY": "test-mcp-key",
}
for _k, _v in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/financial_assistant_test",
)


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DB_URL, pool_size=60, max_overflow=20)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
        await s.rollback()
