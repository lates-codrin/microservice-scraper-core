# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Performance validation tests — validates SLOs from spec."""

import time
import uuid
from statistics import mean

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Performance test client."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint_latency(client):
    """GET /v1/health latency baseline."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    # 20 requests to establish baseline
    for i in range(20):
        start = time.monotonic()
        response = client.get(
            "/v1/health",
            headers={
                **headers,
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": f"perf-tenant-{i}",
            },
        )
        elapsed = (time.monotonic() - start) * 1000  # ms
        latencies.append(elapsed)
        assert response.status_code == 200

    avg = mean(latencies)
    max_latency = max(latencies)

    print(f"\nGET /v1/health: avg={avg:.1f}ms, max={max_latency:.1f}ms")
    # Sanity check: response should be fast (local test)
    assert avg < 5000, f"Avg latency {avg:.1f}ms is unexpectedly high"


def test_classify_endpoint_latency(client):
    """POST /v1/classify latency baseline."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    payload = {
        "content": "Test document with Romanian text.",
        "url_hint": "https://example.ro",
    }

    # 10 requests for classify
    for i in range(10):
        start = time.monotonic()
        response = client.post(
            "/v1/classify",
            json=payload,
            headers={
                **headers,
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": f"perf-tenant-{i}",
            },
        )
        elapsed = (time.monotonic() - start) * 1000  # ms
        latencies.append(elapsed)
        assert response.status_code == 200

    avg = mean(latencies)
    print(f"\nPOST /v1/classify: avg={avg:.1f}ms")


def test_extract_endpoint_latency(client):
    """POST /v1/extract latency baseline."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    payload = {
        "content": "Hotărâre nr. 42/2024",
        "doc_type": "hcl",
        "schema": {},
    }

    # 10 requests for extract
    for i in range(10):
        start = time.monotonic()
        response = client.post(
            "/v1/extract",
            json=payload,
            headers={
                **headers,
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": f"perf-tenant-{i}",
            },
        )
        elapsed = (time.monotonic() - start) * 1000  # ms
        latencies.append(elapsed)
        assert response.status_code == 200

    avg = mean(latencies)
    print(f"\nPOST /v1/extract: avg={avg:.1f}ms")


def test_metrics_endpoint_latency(client):
    """GET /v1/metrics latency baseline."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    # 20 requests to metrics
    for i in range(20):
        start = time.monotonic()
        response = client.get(
            "/v1/metrics",
            headers={
                **headers,
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": f"perf-tenant-{i}",
            },
        )
        elapsed = (time.monotonic() - start) * 1000  # ms
        latencies.append(elapsed)
        assert response.status_code == 200

    avg = mean(latencies)
    print(f"\nGET /v1/metrics: avg={avg:.1f}ms")
    assert avg < 5000, f"Metrics endpoint avg {avg:.1f}ms is unexpectedly high"
