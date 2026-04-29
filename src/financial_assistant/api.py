"""HTTP API endpoints for browser UI.

T-068: POST /chat — streaming SSE chat endpoint
T-069: POST /tools/{summarize_month,find_unusual_spend,list_recurring_subscriptions}
T-070: GET /transactions — paginated list with filters
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from financial_assistant.analytics import (
    find_unusual_spend,
    list_recurring_subscriptions,
    summarize_month,
)
from financial_assistant.claude_client import (
    ClaudeError,
    _SYSTEM_PREAMBLE,
    call_claude,
)
from financial_assistant.context_formatter import format_transactions_csv
from financial_assistant.db import get_session
from financial_assistant.queries import get_transactions

log = structlog.get_logger()

router = APIRouter()


# ── T-068: /chat streaming SSE ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    context_months: int = Field(default=3, ge=1, le=24)
    history: list[dict[str, str]] = Field(default_factory=list)


@router.post("/chat")
async def chat_endpoint(body: ChatRequest) -> StreamingResponse:
    """T-068: Stream Claude response as text/event-stream. Protected by session+CSRF middleware."""
    from anthropic import AsyncAnthropic
    from anthropic.types import TextBlockParam
    from financial_assistant.config import get_settings

    s = get_settings()
    today = date.today()
    start_year, start_mon = _months_ago_date(today.year, today.month, body.context_months)
    start = date(start_year, start_mon, 1)

    async with get_session() as db:
        txns = await get_transactions(db, start_date=start, end_date=today)

    ctx, estimated_tokens = format_transactions_csv(txns) if txns else ("(no transaction data)", 0)
    log.info("chat.context", estimated_tokens=estimated_tokens, transaction_count=len(txns) if txns else 0)

    system_blocks: list[TextBlockParam] = [
        {"type": "text", "text": _SYSTEM_PREAMBLE},
        {
            "type": "text",
            "text": f"Transaction data (last {body.context_months} months):\n\n{ctx}",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    # Last 6 turns of history
    history_turns = body.history[-12:]  # 6 pairs = 12 messages
    messages = history_turns + [{"role": "user", "content": body.question}]

    client = AsyncAnthropic(api_key=s.anthropic_api_key)

    async def token_stream():
        async with client.messages.stream(
            model=s.anthropic_model,
            max_tokens=2048,
            system=system_blocks,  # type: ignore[arg-type]
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(token_stream(), media_type="text/event-stream")


# ── T-069: Proxy tool endpoints ──────────────────────────────────���────────────

class SummarizeMonthRequest(BaseModel):
    month: str
    include_categories: bool = True


class FindUnusualSpendRequest(BaseModel):
    month: str
    lookback_months: int = Field(default=3, ge=1, le=12)


class ListRecurringRequest(BaseModel):
    lookback_months: int = Field(default=6, ge=1, le=24)


@router.post("/tools/summarize_month")
async def proxy_summarize_month(body: SummarizeMonthRequest) -> JSONResponse:
    """T-069: HTTP proxy for summarize_month analytics function."""
    async with get_session() as db:
        try:
            text = await summarize_month(db, month=body.month, include_categories=body.include_categories)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse({"result": text})


@router.post("/tools/find_unusual_spend")
async def proxy_find_unusual_spend(body: FindUnusualSpendRequest) -> JSONResponse:
    """T-069: HTTP proxy for find_unusual_spend analytics function."""
    async with get_session() as db:
        try:
            text = await find_unusual_spend(db, month=body.month, lookback_months=body.lookback_months)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse({"result": text})


@router.post("/tools/list_recurring_subscriptions")
async def proxy_list_recurring(body: ListRecurringRequest) -> JSONResponse:
    """T-069: HTTP proxy for list_recurring_subscriptions analytics function."""
    async with get_session() as db:
        try:
            text = await list_recurring_subscriptions(db, lookback_months=body.lookback_months)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse({"result": text})


# ── T-070: GET /transactions paginated list ───────────────────────────────────

@router.get("/transactions")
async def list_transactions(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    bank: Optional[list[str]] = Query(default=None, description="Filter by bank slug(s)"),
    category: Optional[list[str]] = Query(default=None, description="Filter by category"),
    transaction_type: Optional[str] = Query(default=None, description="debit or credit"),
    page: int = Query(default=1, ge=1),
) -> JSONResponse:
    """T-070: Paginated transaction list with date-range and filter support."""
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    page_size = 100
    offset = (page - 1) * page_size

    async with get_session() as db:
        # Fetch with date + optional bank filter (use first bank if only one provided)
        bank_filter = bank[0] if bank and len(bank) == 1 else None
        cat_filter = category[0] if category and len(category) == 1 else None

        all_txns = await get_transactions(
            db,
            start_date=start_date,
            end_date=end_date,
            bank=bank_filter,
            category=cat_filter,
        )

    # Client-side multi-bank / multi-category / type filter for cases with multiple values
    filtered = all_txns
    if bank and len(bank) > 1:
        bank_set = {b.lower() for b in bank}
        filtered = [t for t in filtered if str(t.source_bank).lower() in bank_set]
    if category and len(category) > 1:
        cat_set = {c.lower() for c in category}
        filtered = [t for t in filtered if t.category and t.category.lower() in cat_set]
    if transaction_type:
        filtered = [t for t in filtered if t.transaction_type == transaction_type]

    total = len(filtered)
    page_items = filtered[offset: offset + page_size]

    return JSONResponse({
        "transactions": [_txn_to_dict(t) for t in page_items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    })


def _txn_to_dict(t: Any) -> dict:
    return {
        "id": str(t.id),
        "date": str(t.date),
        "description": t.description,
        "merchant": t.merchant,
        "amount": str(t.amount),
        "transaction_type": t.transaction_type,
        "category": t.category,
        "source_bank": str(t.source_bank),
    }


def _months_ago_date(year: int, month: int, n: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) - n
    return total // 12, total % 12 + 1
