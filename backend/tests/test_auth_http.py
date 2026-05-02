"""Authentication HTTP API tests."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_login_returns_authenticated_session_state(anon_client):
    response = anon_client.post(
        "/auth/login",
        json={"username": "admin", "password": "test-password"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": "admin"}
    assert "pfa_session=" in response.headers["set-cookie"]


def test_invalid_login_rejected(anon_client):
    response = anon_client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid username or password"


def test_protected_route_requires_authentication(anon_client):
    response = anon_client.get("/categories")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"


def test_logout_clears_session_cookie(client):
    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert "pfa_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
