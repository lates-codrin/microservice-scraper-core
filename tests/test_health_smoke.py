from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def test_health_smoke() -> None:
    client = TestClient(app)
    request_id = str(uuid4())
    response = client.get(
        "/v1/health",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "X-Request-ID": request_id,
            "X-Tenant-ID": settings.default_tenant_id,
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == settings.service_version
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["dependencies"]["storage"] == "ok"