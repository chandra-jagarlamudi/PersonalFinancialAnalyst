"""OpenRouter-backed category suggestion constrained to existing categories."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def suggest_category_slug(
    *,
    description_normalized: str,
    description_raw: str,
    categories: list[dict[str, Any]],
    timeout_sec: float = 30.0,
) -> tuple[str | None, str | None]:
    """Returns (matched_slug_or_none, error_message_or_none).

    categories: rows with keys id, slug, name (slug unique).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None, "OPENROUTER_API_KEY is not set"

    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
    slug_set = {c["slug"] for c in categories}
    catalog = [{"slug": c["slug"], "name": c["name"]} for c in categories]

    system = (
        "You classify personal finance transactions into ONE category from the provided catalog only. "
        "Respond with a single JSON object: {\"slug\": \"<catalog slug>\", \"confidence\": 0.0-1.0, \"reason\": \"short\"}. "
        "The slug MUST exactly match one of the catalog slugs. If uncertain, pick the closest slug anyway "
        'or use slug "uncategorized" only if present in the catalog.'
    )
    user = json.dumps(
        {
            "description_normalized": description_normalized,
            "description_raw": description_raw,
            "catalog": catalog,
        }
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    ref = os.environ.get("OPENROUTER_HTTP_REFERER")
    if ref:
        headers["HTTP-Referer"] = ref

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content)
        slug = str(obj.get("slug", "")).strip()
        if slug not in slug_set:
            return None, f"model returned invalid slug: {slug!r}"
        return slug, None
    except Exception as exc:
        return None, str(exc)
