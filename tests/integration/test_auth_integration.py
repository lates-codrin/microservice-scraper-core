"""Integration tests for AuthHeadersMiddleware + HeaderValidationMiddleware
exercised through the full ASGI stack."""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Authorization header tests
# ---------------------------------------------------------------------------


def test_missing_auth_header_returns_401(client):
    resp = client.post("/v1/scrape", json={"url": "https://example.com", "mode": "sync"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "unauthorized"
    assert "Bearer" in body["error"]["message"]


def test_auth_not_bearer_prefix_returns_401(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={"Authorization": "Basic dGVzdDp0ZXN0", "X-Request-ID": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert "Bearer" in resp.json()["error"]["message"]


def test_auth_empty_bearer_token_returns_401(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={"Authorization": "Bearer ", "X-Request-ID": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert "token is missing" in resp.json()["error"]["message"].lower()


def test_auth_wrong_api_key_returns_401(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={
            "Authorization": "Bearer wrong-api-key",
            "X-Request-ID": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert "invalid" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# X-Request-ID validation tests
# ---------------------------------------------------------------------------


def test_missing_x_request_id_returns_400(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={"Authorization": "Bearer dev-api-key-change-me"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"
    assert "X-Request-ID" in body["error"]["message"]


def test_x_request_id_with_newline_rejected_400(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": "abc\ndef",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"
    assert "X-Request-ID" in body["error"]["message"]


def test_x_request_id_not_valid_uuid_returns_400(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": "not-a-valid-uuid",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"
    assert "UUID" in body["error"]["message"]


# ---------------------------------------------------------------------------
# X-Tenant-ID validation tests
# ---------------------------------------------------------------------------


def test_missing_x_tenant_id_returns_403(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "forbidden"
    assert "X-Tenant-ID" in body["error"]["message"]


def test_x_tenant_id_with_control_chars_rejected_400(client):
    resp = client.post(
        "/v1/scrape",
        json={"url": "https://example.com", "mode": "sync"},
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "tenant\rinjected",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"


# ---------------------------------------------------------------------------
# Public path bypass
# ---------------------------------------------------------------------------


def test_health_endpoint_bypasses_auth(client):
    """GET /v1/health is in PUBLIC_PATHS — no auth required."""
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")


def test_metrics_endpoint_requires_auth(client):
    """GET /v1/metrics is NOT a public path — requires auth headers."""
    resp = client.get("/v1/metrics")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
