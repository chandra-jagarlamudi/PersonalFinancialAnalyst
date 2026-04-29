"""T-059/T-060: Anthropic Claude API client wrapper with prompt caching.

Provides a single async call function used by all analytics functions.
Cache breakpoint placed after system prompt + transaction context block (T-060).
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from anthropic import APIError, AsyncAnthropic, RateLimitError
from anthropic.types import MessageParam, TextBlockParam

from financial_assistant.config import get_settings

log = structlog.get_logger()

_SYSTEM_PREAMBLE = (
    "You are a personal finance analyst assistant. "
    "You have been given the user's transaction data in CSV format. "
    "Analyze the data accurately and concisely. "
    "Refer to amounts in USD. "
    "Focus only on what the data supports."
)

_DEFAULT_MAX_TOKENS = 1024


def _get_client() -> AsyncAnthropic:
    s = get_settings()
    return AsyncAnthropic(api_key=s.anthropic_api_key)


async def call_claude(
    user_message: str,
    transaction_context: Optional[str] = None,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    extra_metadata: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, int]]:
    """Call Claude and return (text_response, usage_dict).

    T-059: Uses model from settings, maps API errors to typed messages.
    T-060: Places cache breakpoint after system prompt + transaction context.

    usage_dict keys: input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens.
    """
    s = get_settings()
    client = _get_client()

    # Build system as a list of TextBlockParam — cache breakpoint on last block.
    system_blocks: list[TextBlockParam] = [
        {"type": "text", "text": _SYSTEM_PREAMBLE},
    ]
    if transaction_context:
        system_blocks.append({
            "type": "text",
            "text": f"Transaction data:\n\n{transaction_context}",
            "cache_control": {"type": "ephemeral"},
        })
    else:
        # No context — put cache control on preamble
        system_blocks[0] = {  # type: ignore[misc]
            "type": "text",
            "text": _SYSTEM_PREAMBLE,
            "cache_control": {"type": "ephemeral"},
        }

    messages: list[MessageParam] = [{"role": "user", "content": user_message}]

    try:
        response = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=max_tokens,
            system=system_blocks,  # type: ignore[arg-type]
            messages=messages,
        )
    except RateLimitError as exc:
        raise ClaudeRateLimitError(
            "Claude API rate limit reached. Retry after a short delay."
        ) from exc
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        if status == 401:
            raise ClaudeAuthError(
                "ANTHROPIC_API_KEY is invalid or missing. Check your configuration."
            ) from exc
        raise ClaudeAPIError(f"Claude API error (status={status}): {exc}") from exc

    text = _extract_text(response)
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(
            response.usage, "cache_creation_input_tokens", 0
        ) or 0,
        "cache_read_input_tokens": getattr(
            response.usage, "cache_read_input_tokens", 0
        ) or 0,
    }

    log.info(
        "claude.call",
        model=s.anthropic_model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cache_creation=usage["cache_creation_input_tokens"],
        cache_read=usage["cache_read_input_tokens"],
        **(extra_metadata or {}),
    )
    return text, usage


def _extract_text(response: Any) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


# ── Typed error hierarchy ─────────────────────────────────────────────────────

class ClaudeError(Exception):
    """Base class for Claude client errors."""


class ClaudeRateLimitError(ClaudeError):
    """Rate limit reached; caller should surface retry guidance."""


class ClaudeAuthError(ClaudeError):
    """API key invalid or missing."""


class ClaudeAPIError(ClaudeError):
    """Unclassified API error."""
