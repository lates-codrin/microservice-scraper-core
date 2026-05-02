"""Integration tests for RateLimitMiddleware with real Redis."""

from __future__ import annotations

import time

from tests.integration.conftest import _auth_headers


def test_rate_limit_headers_present_on_200(client):
    resp = client.post(
        "/v1/classify",
        json={"content": "test"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert "RateLimit-Limit" in resp.headers
    assert "RateLimit-Remaining" in resp.headers
    assert "RateLimit-Reset" in resp.headers
    assert int(resp.headers["RateLimit-Remaining"]) >= 0


def test_rate_limit_exceeded_returns_429(client, monkeypatch):
    import app.middleware.rate_limit as rl_module

    monkeypatch.setattr(rl_module, "RATE_LIMIT", 3)

    headers = _auth_headers()
    for i in range(3):
        resp = client.post(
            "/v1/classify",
            json={"content": "test"},
            headers=headers,
        )
        assert resp.status_code == 200, f"Request {i + 1} expected 200, got {resp.status_code}"

    resp = client.post(
        "/v1/classify",
        json={"content": "test"},
        headers=headers,
    )
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]


def test_rate_limit_429_headers_correct(client, monkeypatch):
    import app.middleware.rate_limit as rl_module

    monkeypatch.setattr(rl_module, "RATE_LIMIT", 2)

    headers = _auth_headers()
    for _ in range(2):
        client.post("/v1/classify", json={"content": "test"}, headers=headers)

    resp = client.post("/v1/classify", json={"content": "test"}, headers=headers)
    assert resp.status_code == 429
    assert resp.headers["RateLimit-Remaining"] == "0"
    assert "Retry-After" in resp.headers
    assert "RateLimit-Reset" in resp.headers


def test_rate_limit_per_tenant_isolation(client, monkeypatch):
    import app.middleware.rate_limit as rl_module

    monkeypatch.setattr(rl_module, "RATE_LIMIT", 2)

    # Exhaust tenant A's limit
    headers_a = _auth_headers(tenant_id="tenant-a")
    for _ in range(2):
        resp = client.post("/v1/classify", json={"content": "test"}, headers=headers_a)
        assert resp.status_code == 200

    # Tenant A should now be rate limited
    resp = client.post("/v1/classify", json={"content": "test"}, headers=headers_a)
    assert resp.status_code == 429

    # Tenant B should still have a fresh bucket
    headers_b = _auth_headers(tenant_id="tenant-b")
    resp = client.post("/v1/classify", json={"content": "test"}, headers=headers_b)
    assert resp.status_code == 200


def test_rate_limit_reset_after_window(client, monkeypatch):
    import app.middleware.rate_limit as rl_module

    monkeypatch.setattr(rl_module, "RATE_LIMIT", 2)
    monkeypatch.setattr(rl_module, "RATE_WINDOW", 1)

    headers = _auth_headers()

    for _ in range(2):
        resp = client.post("/v1/classify", json={"content": "test"}, headers=headers)
        assert resp.status_code == 200

    resp = client.post("/v1/classify", json={"content": "test"}, headers=headers)
    assert resp.status_code == 429

    # Wait for the window to roll over (window is 1 second)
    time.sleep(1.5)

    resp = client.post("/v1/classify", json={"content": "test"}, headers=headers)
    assert resp.status_code == 200
