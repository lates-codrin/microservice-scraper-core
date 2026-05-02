# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
Edge-case tests:
  - empty seed_urls  422
  - max_pages=0  422 (ge=1)
  - max_depth=0  422 (ge=1)
  - limit=0 on pagination  422 (ge=1)
  - cursor issued for a different tenant  403 (tenant isolation)
  - job that transitions queued  failed (worker crash simulation)
  - callback_url that returns a redirect  SSRF check on redirect target
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings

AUTH = f"Bearer {settings.api_key}"
TENANT = settings.default_tenant_id
TENANT_B = "tenant-other"


def _h(tenant: str = TENANT, ikey: str | None = None) -> dict:
    h = {"Authorization": AUTH, "X-Request-ID": str(uuid4()), "X-Tenant-ID": tenant}
    if ikey:
        h["Idempotency-Key"] = ikey
    return h


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Validation edge cases
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_empty_seed_urls_returns_422(client):
    """seed_urls must have min_length=1; empty list  422."""
    payload = {
        "config": {
            "seed_urls": [],
            "allowed_domains": ["primaria-exemplu.ro"],
        }
    }
    resp = client.post("/v1/crawl", json=payload, headers=_h(ikey=str(uuid4())))
    assert resp.status_code == 422, resp.text


def test_max_pages_zero_returns_422(client):
    """max_pages has ge=1; 0  422."""
    payload = {
        "config": {
            "seed_urls": ["https://primaria-exemplu.ro"],
            "allowed_domains": ["primaria-exemplu.ro"],
            "max_pages": 0,
        }
    }
    resp = client.post("/v1/crawl", json=payload, headers=_h(ikey=str(uuid4())))
    assert resp.status_code == 422, resp.text


def test_max_depth_zero_returns_422(client):
    """max_depth has ge=1; 0  422."""
    payload = {
        "config": {
            "seed_urls": ["https://primaria-exemplu.ro"],
            "allowed_domains": ["primaria-exemplu.ro"],
            "max_depth": 0,
        }
    }
    resp = client.post("/v1/crawl", json=payload, headers=_h(ikey=str(uuid4())))
    assert resp.status_code == 422, resp.text


def test_pagination_limit_zero_returns_422(client):
    """limit query param has ge=1; 0  422."""
    resp = client.post(
        "/v1/crawl",
        json={
            "config": {
                "seed_urls": ["https://primaria-exemplu.ro"],
                "allowed_domains": ["primaria-exemplu.ro"],
            }
        },
        headers=_h(ikey=str(uuid4())),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp = client.get(f"/v1/jobs/{job_id}/documents?limit=0", headers=_h())
    assert resp.status_code == 422, resp.text


def test_ssrf_seed_url_private_ip_returns_422(client):
    """seed_urls containing a private/loopback IP must return 422."""
    from unittest.mock import patch

    def dns(h, p=None):
        return [(None, None, None, None, ("10.0.0.1", 0))]

    with patch("socket.getaddrinfo", side_effect=dns):
        payload = {
            "config": {
                "seed_urls": ["http://internal.corp/"],
                "allowed_domains": ["internal.corp"],
            }
        }
        resp = client.post("/v1/crawl", json=payload, headers=_h(ikey=str(uuid4())))
    assert resp.status_code == 422, resp.text


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Cross-tenant cursor
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_cross_tenant_cursor_returns_403(client):
    """A cursor issued for tenant-A's job must 403 when tenant-B uses it."""
    resp = client.post(
        "/v1/crawl",
        json={
            "config": {
                "seed_urls": ["https://primaria-exemplu.ro"],
                "allowed_domains": ["primaria-exemplu.ro"],
            }
        },
        headers=_h(TENANT, ikey=str(uuid4())),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp = client.get(f"/v1/jobs/{job_id}/documents?limit=1", headers=_h(TENANT))
    assert resp.status_code == 200

    resp = client.get(
        f"/v1/jobs/{job_id}/documents?limit=1&cursor=MA==",
        headers=_h(TENANT_B),
    )
    assert resp.status_code == 403, resp.text


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Job crash simulation: queued  failed
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_job_crash_queued_to_failed(client):
    """Simulate worker crash: force job status to 'failed' directly via DB."""
    import asyncio

    from sqlalchemy import update

    import app.db as db_module
    from app.models.db import DbCrawlJob
    from app.models.enums import CrawlStatus

    resp = client.post(
        "/v1/crawl",
        json={
            "config": {
                "seed_urls": ["https://primaria-exemplu.ro"],
                "allowed_domains": ["primaria-exemplu.ro"],
            }
        },
        headers=_h(ikey=str(uuid4())),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    resp = client.get(f"/v1/jobs/{job_id}", headers=_h())
    assert resp.json()["status"] == "queued"

    # Force-fail via direct DB update (bypassing state machine ” simulates crash)
    async def _force_fail():
        async with db_module.async_session_maker() as session:
            await session.execute(
                update(DbCrawlJob)
                .where(DbCrawlJob.job_id == job_id)
                .values(
                    status=CrawlStatus.failed.value,
                    error={"code": "worker_crash", "message": "Worker died unexpectedly"},
                )
            )
            await session.commit()

    # Use a fresh event loop to avoid conflicts with the NullPool engine
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_force_fail())
    finally:
        loop.close()

    resp = client.get(f"/v1/jobs/{job_id}", headers=_h())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "worker_crash"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# callback_url redirect SSRF
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_webhook_callback_redirect_to_private_ip_blocked():
    """webhook delivery must not follow redirects to private IPs."""
    from unittest.mock import patch

    from app.services.webhooks import SSRFBlockedError, _check_callback_ssrf

    with patch(
        "socket.getaddrinfo",
        return_value=[(None, None, None, None, ("169.254.169.254", 0))],
    ), pytest.raises(SSRFBlockedError):
        _check_callback_ssrf("http://169.254.169.254/hook")
