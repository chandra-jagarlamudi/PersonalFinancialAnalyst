"""Analytics unit tests (T-058–T-063).

Context formatter, Claude client error mapping, and analytics functions
with mocked Claude API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from financial_assistant.context_formatter import format_transactions_csv
from financial_assistant.analytics import (
    _parse_month,
    _month_end,
    _months_ago,
    find_unusual_spend,
    list_recurring_subscriptions,
    summarize_month,
)


# ── Stub transaction ──────────────────────────────────────────────────────────

@dataclass
class FakeTxn:
    date: date
    description: str
    amount: Decimal
    transaction_type: str
    category: str | None = None


def _txn(d: str, desc: str, amount: float, tx_type: str = "debit", cat: str | None = None) -> FakeTxn:
    y, m, day = d.split("-")
    return FakeTxn(
        date=date(int(y), int(m), int(day)),
        description=desc,
        amount=Decimal(str(amount)),
        transaction_type=tx_type,
        category=cat,
    )


# ── T-058: Context formatter ──────────────────────────────────────────────────

def test_format_csv_header_and_rows():
    txns = [_txn("2024-01-15", "AMAZON", 29.99, cat="Shopping")]
    csv_str, tokens = format_transactions_csv(txns)
    lines = csv_str.strip().splitlines()
    assert lines[0] == "date,description,amount,type,category"
    assert "AMAZON" in lines[1]
    assert "29.99" in lines[1]
    assert tokens > 0


def test_format_csv_truncates_to_max_rows():
    txns = [_txn("2024-01-15", f"MERCHANT_{i}", 10.0) for i in range(100)]
    csv_str, _ = format_transactions_csv(txns, max_rows=10)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 11  # header + 10 data rows


def test_format_csv_most_recent_first():
    txns = [
        _txn("2024-01-01", "EARLY", 5.0),
        _txn("2024-03-01", "LATE", 5.0),
    ]
    csv_str, _ = format_transactions_csv(txns, max_rows=1)
    assert "LATE" in csv_str  # most recent retained


def test_format_csv_no_currency_symbol():
    txns = [_txn("2024-01-15", "SHOP", 99.99)]
    csv_str, _ = format_transactions_csv(txns)
    assert "$" not in csv_str


# ── Helper unit tests ─────────────────────────────────────────────────────────

def test_parse_month_valid():
    assert _parse_month("2024-01") == (2024, 1)
    assert _parse_month("2024-12") == (2024, 12)


def test_parse_month_invalid():
    with pytest.raises(ValueError):
        _parse_month("January 2024")
    with pytest.raises(ValueError):
        _parse_month("2024")


def test_month_end():
    assert _month_end(2024, 1) == date(2024, 1, 31)
    assert _month_end(2024, 2) == date(2024, 2, 29)  # 2024 is a leap year
    assert _month_end(2023, 2) == date(2023, 2, 28)


def test_months_ago():
    assert _months_ago(2024, 3, 3) == (2023, 12)
    assert _months_ago(2024, 1, 1) == (2023, 12)


# ── Analytics functions (mock Claude) ────────────────────────────────────────

MOCK_TXNS = [
    _txn("2024-01-15", "STARBUCKS", 5.50, cat="Food"),
    _txn("2024-01-20", "AMAZON", 29.99, cat="Shopping"),
    _txn("2024-01-25", "PAYCHECK", 2000.00, tx_type="credit", cat="Income"),
]


@pytest.mark.asyncio
async def test_summarize_month_returns_text():
    mock_db = AsyncMock()
    with patch("financial_assistant.analytics.get_transactions", return_value=MOCK_TXNS), \
         patch("financial_assistant.analytics.call_claude", return_value=("Summary text", {})):
        result = await summarize_month(mock_db, "2024-01")
    assert result == "Summary text"


@pytest.mark.asyncio
async def test_summarize_month_raises_on_no_transactions():
    mock_db = AsyncMock()
    with patch("financial_assistant.analytics.get_transactions", return_value=[]):
        with pytest.raises(ValueError, match="No transactions found"):
            await summarize_month(mock_db, "2024-01")


@pytest.mark.asyncio
async def test_find_unusual_spend_returns_text():
    mock_db = AsyncMock()
    with patch("financial_assistant.analytics.get_transactions", return_value=MOCK_TXNS), \
         patch("financial_assistant.analytics.call_claude", return_value=("Nothing unusual.", {})):
        result = await find_unusual_spend(mock_db, "2024-01", lookback_months=2)
    assert "Nothing unusual" in result


@pytest.mark.asyncio
async def test_find_unusual_spend_empty_returns_message():
    mock_db = AsyncMock()
    with patch("financial_assistant.analytics.get_transactions", return_value=[]):
        result = await find_unusual_spend(mock_db, "2024-01")
    assert "No transactions found" in result


@pytest.mark.asyncio
async def test_list_recurring_subscriptions_returns_text():
    mock_db = AsyncMock()
    with patch("financial_assistant.analytics.get_transactions", return_value=MOCK_TXNS), \
         patch("financial_assistant.analytics.call_claude", return_value=("- Netflix: monthly $15.49", {})):
        result = await list_recurring_subscriptions(mock_db, lookback_months=3)
    assert "Netflix" in result


@pytest.mark.asyncio
async def test_analytics_surfaces_claude_error_as_runtime_error():
    from financial_assistant.claude_client import ClaudeRateLimitError
    mock_db = AsyncMock()
    with patch("financial_assistant.analytics.get_transactions", return_value=MOCK_TXNS), \
         patch("financial_assistant.analytics.call_claude", side_effect=ClaudeRateLimitError("rate limit")):
        with pytest.raises(RuntimeError, match="rate limit"):
            await summarize_month(mock_db, "2024-01")


# ── Claude client error mapping ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_claude_maps_rate_limit_error():
    from anthropic import RateLimitError as AnthropicRateLimitError
    from financial_assistant.claude_client import ClaudeRateLimitError, call_claude

    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch("financial_assistant.claude_client._get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=AnthropicRateLimitError("rate limit", response=mock_response, body={})
        )
        mock_client_factory.return_value = mock_client

        with pytest.raises(ClaudeRateLimitError):
            await call_claude("test prompt")
