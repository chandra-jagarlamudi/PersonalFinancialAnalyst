"""MCP tool registration and HTTP proxy tests (T-064–T-070).

T-064: tools/list returns all 3 tools
T-065: missing required param returns isError response (not 500)
T-066: tool exception returns isError with human-readable message
T-069: HTTP proxy endpoints forward to analytics functions
T-070: GET /transactions with filters and pagination
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from financial_assistant.mcp_server import (
    _TOOLS,
    _validate_tool_args,
    handle_list_tools,
    handle_call_tool,
)


# ── T-064: Tool list ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tools_returns_all_three():
    tools = await handle_list_tools()
    names = {t.name for t in tools}
    assert names == {"summarize_month", "find_unusual_spend", "list_recurring_subscriptions"}


def test_tool_schemas_have_required_fields():
    for tool in _TOOLS:
        assert tool.name
        assert tool.description
        assert "properties" in tool.inputSchema


def test_summarize_month_requires_month():
    schema = next(t for t in _TOOLS if t.name == "summarize_month")
    assert "month" in schema.inputSchema.get("required", [])


def test_find_unusual_spend_requires_month():
    schema = next(t for t in _TOOLS if t.name == "find_unusual_spend")
    assert "month" in schema.inputSchema.get("required", [])


# ── T-065: Input validation ───────────────────────────────────────────────────

def test_validate_missing_month():
    err = _validate_tool_args("summarize_month", {})
    assert err is not None
    assert "month" in err


def test_validate_invalid_month_format():
    err = _validate_tool_args("summarize_month", {"month": "January 2024"})
    assert err is not None


def test_validate_valid_month():
    err = _validate_tool_args("summarize_month", {"month": "2024-01"})
    assert err is None


def test_validate_no_required_for_recurring():
    err = _validate_tool_args("list_recurring_subscriptions", {})
    assert err is None


@pytest.mark.asyncio
async def test_call_tool_missing_month_returns_error_content():
    result = await handle_call_tool("summarize_month", {})
    assert len(result) == 1
    assert "error" in result[0].text.lower() or "missing" in result[0].text.lower()


# ── T-066: Tool error handling ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_exception_returns_error_content_not_500():
    with patch("financial_assistant.mcp_server._dispatch_tool", side_effect=RuntimeError("db error")):
        result = await handle_call_tool("summarize_month", {"month": "2024-01"})
    assert len(result) == 1
    assert "db error" in result[0].text.lower() or "failed" in result[0].text.lower()


@pytest.mark.asyncio
async def test_call_tool_success_returns_text_content():
    with patch("financial_assistant.mcp_server._dispatch_tool", return_value="Summary: spent $500"):
        result = await handle_call_tool("summarize_month", {"month": "2024-01"})
    assert result[0].text == "Summary: spent $500"


# ── T-069: HTTP proxy endpoints ───────────────────────────────────────────────

@pytest.fixture
def test_app():
    from fastapi import FastAPI
    from financial_assistant.api import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_proxy_summarize_month():
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from financial_assistant.api import router

    app = FastAPI()
    app.include_router(router)

    with patch("financial_assistant.api.summarize_month", return_value="Summary text"), \
         patch("financial_assistant.api.get_session") as mock_gs:
        mock_db = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_gs.return_value = mock_cm

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/tools/summarize_month", json={"month": "2024-01"})

    assert resp.status_code == 200
    assert resp.json()["result"] == "Summary text"


@pytest.mark.asyncio
async def test_proxy_summarize_month_value_error_returns_422():
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from financial_assistant.api import router

    app = FastAPI()
    app.include_router(router)

    with patch("financial_assistant.api.summarize_month", side_effect=ValueError("No data")), \
         patch("financial_assistant.api.get_session") as mock_gs:
        mock_db = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_gs.return_value = mock_cm

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/tools/summarize_month", json={"month": "2024-01"})

    assert resp.status_code == 422


# ── T-070: GET /transactions ──────────────────────────────────────────────────

@pytest.fixture
def fake_txn():
    m = MagicMock()
    m.id = "abc123"
    m.date = date(2024, 1, 15)
    m.description = "AMAZON"
    m.merchant = "AMAZON"
    m.amount = Decimal("29.99")
    m.transaction_type = "debit"
    m.category = "Shopping"
    m.source_bank = "chase"
    return m


@pytest.mark.asyncio
async def test_list_transactions_returns_page(fake_txn):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from financial_assistant.api import router

    app = FastAPI()
    app.include_router(router)

    with patch("financial_assistant.api.get_transactions", return_value=[fake_txn]), \
         patch("financial_assistant.api.get_session") as mock_gs:
        mock_db = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_gs.return_value = mock_cm

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/transactions",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert len(data["transactions"]) == 1
    assert data["transactions"][0]["description"] == "AMAZON"


@pytest.mark.asyncio
async def test_list_transactions_invalid_date_range(fake_txn):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from financial_assistant.api import router

    app = FastAPI()
    app.include_router(router)

    with patch("financial_assistant.api.get_session") as mock_gs:
        mock_db = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_gs.return_value = mock_cm

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/transactions",
                params={"start_date": "2024-01-31", "end_date": "2024-01-01"},
            )

    assert resp.status_code == 400
