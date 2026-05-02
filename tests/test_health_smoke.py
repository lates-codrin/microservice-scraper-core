# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Smoke test for the /v1/health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def test_health_smoke() -> None:
    """Health endpoint returns 200 with expected structure."""
    client = TestClient(app)
    # Health is a public endpoint ” no auth required
    response = client.get("/v1/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] in ("ok", "degraded")
    assert payload["version"] == settings.service_version
    assert isinstance(payload["uptime_seconds"], int)
    assert "redis" in payload["dependencies"]
    assert "postgres" in payload["dependencies"]
