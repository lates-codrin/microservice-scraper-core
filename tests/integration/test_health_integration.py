"""Integration tests for GET /v1/health — exercises real PostgreSQL and Redis."""

from __future__ import annotations

from app.settings import settings


def test_health_200_with_real_dependencies(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] in ("ok", "degraded")
    assert body["version"] == settings.service_version
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0
    assert isinstance(body["dependencies"], dict)
    assert isinstance(body["queue_depth"], int)
    assert body["queue_depth"] >= 0
    assert isinstance(body["active_workers"], int)
    assert body["active_workers"] >= 0

    deps = body["dependencies"]
    assert "redis" in deps
    assert "postgres" in deps
    assert deps["redis"] in ("ok", "degraded", "down")
    assert deps["postgres"] in ("ok", "degraded", "down")


def test_health_response_matches_model(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()

    required_keys = {
        "status",
        "version",
        "uptime_seconds",
        "dependencies",
        "queue_depth",
        "active_workers",
    }
    assert required_keys.issubset(body.keys())

    assert isinstance(body["dependencies"], dict)
    for dep_value in body["dependencies"].values():
        assert isinstance(dep_value, str)


def test_health_consistent_on_repeated_calls(client):
    first = client.get("/v1/health")
    second = client.get("/v1/health")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["version"] == second.json()["version"]


def test_health_no_auth_required(client):
    """Health endpoint is public — zero headers should still return 200."""
    resp = client.get("/v1/health", headers={})
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")
