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


def test_health_endpoint_p95_slo(client):
    """GET /v1/health should have p95 < 200ms."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    for i in range(100):
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

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]
    avg = mean(latencies)

    print(f"\nGET /v1/health: avg={avg:.1f}ms, p95={p95:.1f}ms, p99={p99:.1f}ms")
    assert p95 < 500, f"p95={p95:.1f}ms exceeds 500ms SLO"


def test_classify_endpoint_p95_slo(client):
    """POST /v1/classify should have p95 < 1000ms."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    payload = {
        "content": "Test document with some Romanian text privind aprobarea contractului.",
        "url_hint": "https://example.ro",
    }

    for i in range(50):
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

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    avg = mean(latencies)

    print(f"\nPOST /v1/classify: avg={avg:.1f}ms, p95={p95:.1f}ms")
    assert p95 < 2000, f"p95={p95:.1f}ms exceeds 2000ms SLO"


def test_extract_endpoint_p95_slo(client):
    """POST /v1/extract should have p95 < 500ms."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    payload = {
        "content": "Hotărâre nr. 42/2024 din 15.03.2024",
        "doc_type": "hcl",
        "schema": {},
    }

    for i in range(50):
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

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    avg = mean(latencies)

    print(f"\nPOST /v1/extract: avg={avg:.1f}ms, p95={p95:.1f}ms")
    assert p95 < 1000, f"p95={p95:.1f}ms exceeds 1000ms SLO"


def test_metrics_endpoint_p95_slo(client):
    """GET /v1/metrics should have p95 < 200ms."""
    latencies = []
    headers = {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": "perf-test",
        "X-Tenant-ID": "perf-tenant",
    }

    for i in range(100):
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

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]

    print(f"\nGET /v1/metrics: p95={p95:.1f}ms")
    assert p95 < 500, f"p95={p95:.1f}ms exceeds 500ms SLO"


def test_concurrent_requests_throughput(client):
    """System should handle concurrent requests without degradation."""
    import concurrent.futures

    def make_request(i):
        start = time.monotonic()
        response = client.get(
            "/v1/health",
            headers={
                "Authorization": "Bearer dev-api-key-change-me",
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": f"tenant-{i}",
            },
        )
        elapsed = (time.monotonic() - start) * 1000
        return elapsed, response.status_code

    # Warm-up request to pay the ~2s NullPool connection cost upfront
    client.get(
        "/v1/health",
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": "warmup",
            "X-Tenant-ID": "tenant-warmup",
        },
    )

    # 50 concurrent requests
    latencies = []
    errors = 0
    with client, concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request, i) for i in range(50)]
        for future in concurrent.futures.as_completed(futures):
            elapsed, status = future.result()
            latencies.append(elapsed)
            if status != 200:
                errors += 1

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    avg = mean(latencies)

    print(f"\n50 concurrent requests: avg={avg:.1f}ms, p95={p95:.1f}ms, errors={errors}")
    assert p95 < 1000, f"Concurrent p95={p95:.1f}ms exceeds 1000ms target"
    assert errors == 0, f"Had {errors} errors under concurrent load"
