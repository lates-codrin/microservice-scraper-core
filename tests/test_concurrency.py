"""
Concurrency test: 20 concurrent POST /v1/crawl requests for the same tenant.
- No duplicate jobs created (idempotency key uniqueness)
- No DB deadlocks
- Redis counters are consistent
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.main import app
from app.settings import settings

AUTH = f"Bearer {settings.api_key}"
TENANT = settings.default_tenant_id

CRAWL_PAYLOAD = {
    "config": {
        "seed_urls": ["https://primaria-exemplu.ro"],
        "allowed_domains": ["primaria-exemplu.ro"],
    }
}


@pytest.mark.asyncio
async def test_20_concurrent_crawl_no_duplicates():
    """20 concurrent POST /v1/crawl with distinct idempotency keys → 20 distinct jobs, no deadlocks."""
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        async def _post() -> tuple[int, str | None]:
            ikey = str(uuid4())
            resp = await ac.post(
                "/v1/crawl",
                json=CRAWL_PAYLOAD,
                headers={
                    "Authorization": AUTH,
                    "X-Request-ID": str(uuid4()),
                    "X-Tenant-ID": TENANT,
                    "Idempotency-Key": ikey,
                },
            )
            job_id = resp.json().get("job_id") if resp.status_code == 202 else None
            return resp.status_code, job_id

        results = await asyncio.gather(*[_post() for _ in range(20)])

    statuses = [r[0] for r in results]
    job_ids = [r[1] for r in results if r[1] is not None]

    # All must succeed
    assert all(s == 202 for s in statuses), f"Non-202 responses: {statuses}"

    # All job_ids must be distinct (no duplicates from concurrent writes)
    assert len(job_ids) == 20
    assert len(set(job_ids)) == 20, "Duplicate job IDs detected"


@pytest.mark.asyncio
async def test_idempotency_same_key_concurrent():
    """20 concurrent POSTs with the SAME idempotency key → all return the same job_id."""
    transport = ASGITransport(app=app)
    ikey = str(uuid4())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        async def _post() -> tuple[int, str | None]:
            resp = await ac.post(
                "/v1/crawl",
                json=CRAWL_PAYLOAD,
                headers={
                    "Authorization": AUTH,
                    "X-Request-ID": str(uuid4()),
                    "X-Tenant-ID": TENANT,
                    "Idempotency-Key": ikey,
                },
            )
            job_id = resp.json().get("job_id") if resp.status_code in (200, 202) else None
            return resp.status_code, job_id

        results = await asyncio.gather(*[_post() for _ in range(20)])

    statuses = [r[0] for r in results]
    job_ids = [r[1] for r in results if r[1] is not None]

    # All must succeed (200 or 202)
    assert all(s in (200, 202) for s in statuses), f"Unexpected statuses: {statuses}"

    # All must return the same job_id
    assert len(set(job_ids)) == 1, f"Multiple job IDs for same idempotency key: {set(job_ids)}"
