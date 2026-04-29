# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for rate limiting enforcement."""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_AUTH = "Bearer dev-api-key-change-me"


@pytest.fixture
def client():
    """Rate limit test client."""
    app = create_app()
    yield TestClient(app)


def test_rate_limit_headers_present(client):
    """All responses include RateLimit-* headers."""
    response = client.get(
        "/v1/health",
        headers={
            "Authorization": _AUTH,
            "X-Request-ID": "test-req-id",
            "X-Tenant-ID": "test-tenant-headers",
        },
    )

    assert response.status_code == 200
    assert "RateLimit-Limit" in response.headers
    assert "RateLimit-Remaining" in response.headers
    assert "RateLimit-Reset" in response.headers


def test_rate_limit_counter_increments(client):
    """Rate limit counter decrements with each request for the same tenant."""
    # Use a dedicated tenant so the conftest flush gives us a clean slate.
    headers = {
        "Authorization": _AUTH,
        "X-Request-ID": "test-req-1",
        "X-Tenant-ID": "test-tenant-counter",
    }

    response1 = client.get("/v1/health", headers=headers)
    assert response1.status_code == 200, (
        f"First request failed: {response1.status_code} {response1.text}"
    )
    remaining1 = int(response1.headers["RateLimit-Remaining"])

    response2 = client.get(
        "/v1/health", headers={**headers, "X-Request-ID": "test-req-2"}
    )
    assert response2.status_code == 200, (
        f"Second request failed: {response2.status_code} {response2.text}"
    )
    remaining2 = int(response2.headers["RateLimit-Remaining"])

    # After the second request the bucket has one more hit, so remaining
    # must be strictly lower than after the first.
    assert remaining2 < remaining1, (
        f"Expected remaining to decrease: {remaining1} -> {remaining2}"
    )


def test_rate_limit_scoped_per_tenant(client):
    """Rate limits are scoped per tenant — two tenants don't share a bucket."""
    headers_a = {
        "Authorization": _AUTH,
        "X-Request-ID": "test-a",
        "X-Tenant-ID": "tenant-scope-a",
    }
    headers_b = {
        "Authorization": _AUTH,
        "X-Request-ID": "test-b",
        "X-Tenant-ID": "tenant-scope-b",
    }

    response_a = client.get("/v1/health", headers=headers_a)
    response_b = client.get("/v1/health", headers=headers_b)

    assert response_a.status_code == 200
    assert response_b.status_code == 200

    remaining_a = int(response_a.headers["RateLimit-Remaining"])
    remaining_b = int(response_b.headers["RateLimit-Remaining"])

    # Each tenant starts from the same full quota, so both should be equal
    # after exactly one request each (both at RATE_LIMIT - 1).
    assert remaining_a == remaining_b, (
        "Different tenants should start from the same quota; "
        f"got {remaining_a} vs {remaining_b}"
    )
    assert remaining_a >= 0
    assert remaining_b >= 0


def test_rate_limit_reset_header(client):
    """RateLimit-Reset header indicates the start of the next window."""
    response = client.get(
        "/v1/health",
        headers={
            "Authorization": _AUTH,
            "X-Request-ID": "test-reset",
            "X-Tenant-ID": "test-tenant-reset",
        },
    )

    assert response.status_code == 200

    reset_timestamp = int(response.headers["RateLimit-Reset"])
    current_time = int(time.time())

    # Reset must be in the future but no more than one full window away.
    assert reset_timestamp > current_time, "Reset timestamp must be in the future"
    assert reset_timestamp <= current_time + 70, (
        "Reset timestamp is unexpectedly far in the future"
    )


def test_rate_limit_enforcement(client):
    """Requests beyond the quota receive HTTP 429."""
    import os
    from app.middleware.rate_limit import RATE_LIMIT

    # This test only makes sense when the ceiling is reachable in a test run.
    # With the default test override of 10 000 it would take too long, so we
    # skip unless someone has set a deliberately low limit for this purpose.
    if RATE_LIMIT > 20:
        pytest.skip("RATE_LIMIT too high to exhaust in a unit test (set <= 20 to run)")

    tenant = "test-tenant-enforce"
    headers = {"Authorization": _AUTH, "X-Tenant-ID": tenant}

    # Exhaust the quota.
    for i in range(RATE_LIMIT):
        r = client.get("/v1/health", headers={**headers, "X-Request-ID": f"req-{i}"})
        assert r.status_code == 200, f"Request {i} failed before limit was reached"

    # The very next request must be rejected.
    over = client.get(
        "/v1/health", headers={**headers, "X-Request-ID": "req-over"}
    )
    assert over.status_code == 429
    assert "Retry-After" in over.headers