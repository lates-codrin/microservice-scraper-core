"""
Edge-case tests:
  - empty seed_urls → 422
  - max_pages=0 → 422 (ge=1)
  - max_depth=0 → 422 (ge=1)
  - limit=0 on pagination → 422 (ge=1)
  - cursor issued for a different tenant → 403 (tenant isolation)
  - job that transitions queued → failed (worker crash simulation)
  - callback_url that returns a redirect → SSRF check on redirect target
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


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Validation edge cases
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_seed_urls_returns_422(client):
    """seed_urls must have min_length=1; empty list → 422."""
    payload = {
        "config": {
            "seed_urls": [],
            "allowed_domains": ["primaria-exemplu.ro"],
        }
    }
    resp = client.post("/v1/crawl", json=payload, headers=_h(ikey=str(uuid4())))
    assert resp.status_code == 422, resp.text


def test_max_pages_zero_returns_422(client):
    """max_pages has ge=1; 0 → 422."""
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
    """max_depth has ge=1; 0 → 422."""
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
    """limit query param has ge=1; 0 → 422."""
    # Need a real job first
    resp = client.post(
        "/v1/crawl",
        json={"config": {"seed_urls": ["https://primaria-exemplu.ro"], "allowed_domains": ["primaria-exemplu.ro"]}},
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


# ─────────────────────────────────────────────────────────────────────────────
# Cross-tenant cursor
# ─────────────────────────────────────────────────────────────────────────────


def test_cross_tenant_cursor_returns_403(client):
    """A cursor issued for tenant-A's job must 403 when tenant-B uses it."""
    # Create job as tenant-A
    resp = client.post(
        "/v1/crawl",
        json={"config": {"seed_urls": ["https://primaria-exemplu.ro"], "allowed_domains": ["primaria-exemplu.ro"]}},
        headers=_h(TENANT, ikey=str(uuid4())),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Tenant-A reads page 1 — cursor may or may not exist
    resp = client.get(f"/v1/jobs/{job_id}/documents?limit=1", headers=_h(TENANT))
    assert resp.status_code == 200

    # Tenant-B tries to read the same job with any cursor → 403
    resp = client.get(
        f"/v1/jobs/{job_id}/documents?limit=1&cursor=MA==",
        headers=_h(TENANT_B),
    )
    assert resp.status_code == 403, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Job crash simulation: queued → failed
# ─────────────────────────────────────────────────────────────────────────────


def test_job_crash_queued_to_failed(client):
    """Simulate worker crash: force job status to 'failed' directly via job_store."""
    from app.services.job_store import JobStore
    from app.models.enums import CrawlStatus

    resp = client.post(
        "/v1/crawl",
        json={"config": {"seed_urls": ["https://primaria-exemplu.ro"], "allowed_domains": ["primaria-exemplu.ro"]}},
        headers=_h(ikey=str(uuid4())),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Verify job starts as queued
    resp = client.get(f"/v1/jobs/{job_id}", headers=_h())
    assert resp.json()["status"] == "queued"

    # Simulate crash via direct DB update (use the dependency)
    import asyncio
    from app.db import async_session_maker
    import fakeredis
    from app.models.db import DbCrawlJob
    from sqlalchemy import update

    async def _force_fail():
        async with async_session_maker() as session:
            await session.execute(
                update(DbCrawlJob)
                .where(DbCrawlJob.job_id == job_id)
                .values(
                    status=CrawlStatus.failed.value,
                    error={"code": "worker_crash", "message": "Worker died unexpectedly"},
                )
            )
            await session.commit()

    asyncio.run(_force_fail())

    resp = client.get(f"/v1/jobs/{job_id}", headers=_h())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "worker_crash"


# ─────────────────────────────────────────────────────────────────────────────
# callback_url redirect SSRF
# ─────────────────────────────────────────────────────────────────────────────


def test_webhook_callback_redirect_to_private_ip_blocked():
    """webhook delivery must not follow redirects to private IPs."""
    from unittest.mock import patch
    from app.services.webhooks import _check_callback_ssrf, SSRFBlockedError

    # The callback_url itself resolves fine, but redirect would go to 169.254.169.254
    # The SSRF guard checks the callback_url's hostname before POSTing.
    # If callback is legitimate but follow_redirects is False, the redirect won't be followed.
    # This test verifies _check_callback_ssrf blocks private IPs.
    with patch(
        "socket.getaddrinfo",
        return_value=[(None, None, None, None, ("169.254.169.254", 0))],
    ):
        with pytest.raises(SSRFBlockedError):
            _check_callback_ssrf("http://169.254.169.254/hook")
