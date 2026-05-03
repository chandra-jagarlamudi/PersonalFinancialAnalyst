import json
from unittest.mock import MagicMock, patch

from pfa.llm_category_suggest import suggest_category_slug


def test_returns_none_when_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    slug, err = suggest_category_slug(
        description_normalized="starbucks",
        description_raw="STARBUCKS",
        categories=[{"id": "1", "slug": "dining", "name": "Dining"}],
    )
    assert slug is None
    assert "OPENROUTER_API_KEY" in (err or "")


def test_maps_json_slug(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    fake_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"slug": "dining", "confidence": 0.9, "reason": "coffee"}
                    )
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_response
    mock_inst = MagicMock()
    mock_inst.post.return_value = mock_resp
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_inst
    mock_cm.__exit__.return_value = None
    with patch("pfa.llm_category_suggest.httpx.Client", return_value=mock_cm):
        slug, err = suggest_category_slug(
            description_normalized="starbucks",
            description_raw="X",
            categories=[{"id": "a", "slug": "dining", "name": "Dining"}],
        )
    assert err is None
    assert slug == "dining"


def test_invalid_slug_from_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    fake_response = {
        "choices": [
            {"message": {"content": json.dumps({"slug": "fake-slug", "confidence": 1.0})}}
        ]
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_response
    mock_inst = MagicMock()
    mock_inst.post.return_value = mock_resp
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_inst
    mock_cm.__exit__.return_value = None
    with patch("pfa.llm_category_suggest.httpx.Client", return_value=mock_cm):
        slug, err = suggest_category_slug(
            description_normalized="x",
            description_raw="y",
            categories=[{"id": "a", "slug": "dining", "name": "Dining"}],
        )
    assert slug is None
    assert err is not None
    assert "invalid slug" in err.lower()
