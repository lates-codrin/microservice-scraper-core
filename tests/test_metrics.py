# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for metrics endpoint and collection."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.metrics import get_metrics
import uuid


@pytest.fixture
def client():
    """Metrics test client."""
    app = create_app()
    yield TestClient(app)


def test_metrics_endpoint_returns_prometheus_format(client):
    """GET /v1/metrics returns Prometheus exposition format."""
    # Record some test requests
    metrics = get_metrics()
    metrics.record_http_request("GET", 200, "/v1/health", 0.1)
    metrics.record_http_request("POST", 202, "/v1/crawl", 0.5)
    metrics.record_http_request("GET", 404, "/v1/jobs/missing", 0.05)

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    
    body = response.text
    assert "# HELP http_requests_total" in body
    assert "# TYPE http_requests_total counter" in body
    assert 'method="GET"' in body
    assert 'status="200"' in body
    assert 'endpoint="/v1/health"' in body


def test_metrics_http_request_duration_histogram(client):
    """Metrics include p50, p95, p99 latency histograms."""
    metrics = get_metrics()
    
    # Record requests with different latencies
    for latency in [0.01, 0.02, 0.03, 0.05, 0.10, 0.20, 0.30, 0.50, 0.80, 1.0]:
        metrics.record_http_request("GET", 200, "/v1/health", latency)

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    body = response.text
    
    assert "# HELP http_request_duration_seconds" in body
    assert "# TYPE http_request_duration_seconds histogram" in body
    assert 'quantile="0.5"' in body
    assert 'quantile="0.95"' in body
    assert 'quantile="0.99"' in body


def test_metrics_cost_tracking(client):
    """Metrics track vendor cost in USD."""
    metrics = get_metrics()
    metrics.record_cost(10.50)
    metrics.record_cost(5.25)

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    body = response.text
    
    assert "# HELP vendor_cost_usd_total" in body
    assert "# TYPE vendor_cost_usd_total counter" in body
    assert "vendor_cost_usd_total 15.75" in body


def test_metrics_token_tracking(client):
    """Metrics track input/output tokens separately."""
    metrics = get_metrics()
    metrics.record_tokens("input", 1000)
    metrics.record_tokens("output", 500)
    metrics.record_tokens("input", 300)

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    body = response.text
    
    assert "# HELP vendor_tokens_total" in body
    assert 'direction="input"' in body
    assert 'direction="output"' in body
    assert 'vendor_tokens_total{direction="input"} 1300' in body
    assert 'vendor_tokens_total{direction="output"} 500' in body


def test_metrics_external_api_errors(client):
    """Metrics track external API errors by dependency and type."""
    metrics = get_metrics()
    metrics.record_external_api_error("postgres", "connection_timeout")
    metrics.record_external_api_error("postgres", "connection_timeout")
    metrics.record_external_api_error("redis", "socket_error")

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    body = response.text
    
    assert "# HELP vendor_external_api_errors_total" in body
    assert 'dependency="postgres"' in body
    assert 'error_type="connection_timeout"' in body
    assert 'dependency="redis"' in body


def test_metrics_active_jobs_gauge(client):
    """Metrics include active_jobs gauge."""
    metrics = get_metrics()
    metrics.set_active_jobs(5)

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    body = response.text
    
    assert "# HELP active_jobs" in body
    assert "# TYPE active_jobs gauge" in body
    assert "active_jobs 5" in body


def test_metrics_documents_scraped_counter(client):
    """Metrics track total documents scraped."""
    metrics = get_metrics()
    for _ in range(42):
        metrics.record_document_scraped()

    response = client.get("/v1/metrics", headers={"Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": str(uuid.uuid4()), "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}"})
    body = response.text
    
    assert "# HELP documents_scraped_total" in body
    assert "# TYPE documents_scraped_total counter" in body
    assert "documents_scraped_total 42" in body
