# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for incremental crawling, deduplication, pagination, and 410 Gone."""

import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.settings import settings

AUTH = f"Bearer {settings.api_key}"
TENANT_A = settings.default_tenant_id


def _h(tenant: str = TENANT_A, ikey: str | None = None) -> dict:
    h = {
        "X-Tenant-ID": tenant,
        "Authorization": AUTH,
        "X-Request-ID": str(uuid4()),
    }
    if ikey:
        h["Idempotency-Key"] = ikey
    return h


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _create_crawl(client, seed_url: str = "https://example.ro") -> dict:
    """Create a crawl job and return the JSON response."""
    resp = client.post(
        "/v1/crawl",
        headers=_h(ikey=str(uuid4())),
        json={
            "config": {
                "seed_urls": [seed_url],
                "allowed_domains": ["example.ro"],
            }
        },
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


def test_pagination_empty_documents(client):
    """A freshly-created job returns empty documents page."""
    job_data = _create_crawl(client)
    job_id = job_data["job_id"]

    res = client.get(f"/v1/jobs/{job_id}/documents?limit=1", headers=_h())
    assert res.status_code == 200
    data = res.json()
    assert data["documents"] == []
    assert data["has_more"] is False


def test_tenant_isolation(client):
    """Tenant B cannot read tenant A's job  403."""
    job_data = _create_crawl(client)
    job_id = job_data["job_id"]

    res_b = client.get(f"/v1/jobs/{job_id}/documents", headers=_h("tenant_b"))
    assert res_b.status_code == 403


def test_idempotency_returns_same_job(client):
    """Same Idempotency-Key with same body returns the existing job."""
    idem_key = str(uuid4())
    body = {"config": {"seed_urls": ["https://example.ro"], "allowed_domains": ["example.ro"]}}

    resp1 = client.post("/v1/crawl", headers=_h(ikey=idem_key), json=body)
    resp2 = client.post("/v1/crawl", headers=_h(ikey=idem_key), json=body)

    assert resp1.status_code == 202
    assert resp2.json()["job_id"] == resp1.json()["job_id"]

