import pytest
import fakeredis
import base64
import json
from datetime import datetime, timedelta, UTC
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.services.job_store import InMemoryJobStore
from app.models.crawl import CrawlConfig, IncrementalOptions
from app.models.enums import CrawlStatus

client = TestClient(app)

@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)

@pytest.fixture
def store(fake_redis):
    store = InMemoryJobStore(redis_client=fake_redis)
    app.state.job_store = store
    return store

def test_incremental_dedup(store, fake_redis):
    # Create crawl job with known hashes
    job = store.create_crawl_job(
        "tenant_a",
        CrawlConfig(seed_urls=["http://x.com"], allowed_domains=["x.com"]),
        idempotency_key="key1",
        request_fingerprint="fp1",
        incremental=IncrementalOptions(known_content_hashes=["hash1", "hash2"])
    )
    
    # Assert hashes are in redis
    assert fake_redis.sismember(f"JOB:known_hashes:{job.job_id}", "hash1")
    assert fake_redis.sismember(f"JOB:known_hashes:{job.job_id}", "hash2")

def test_pagination_and_isolation(store, fake_redis):
    job = store.create_crawl_job(
        "tenant_a",
        CrawlConfig(seed_urls=["http://x.com"], allowed_domains=["x.com"]),
        idempotency_key="key2",
        request_fingerprint="fp2"
    )
    
    headers_a = {"X-Tenant-ID": "tenant_a", "Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": "00000000-0000-4000-8000-000000000001"}
    headers_b = {"X-Tenant-ID": "tenant_b", "Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": "00000000-0000-4000-8000-000000000001"}
    
    # tenant B cannot read tenant A's job -> 403
    res_b = client.get(f"/v1/jobs/{job.job_id}/documents", headers=headers_b)
    assert res_b.status_code == 403
    
    # tenant A can
    res_a = client.get(f"/v1/jobs/{job.job_id}/documents?limit=1", headers=headers_a)
    assert res_a.status_code == 200
    data = res_a.json()
    assert len(data["documents"]) <= 1
    
    # cursor pagination round-trip
    if data["has_more"]:
        cursor = data["next_cursor"]
        res_a_next = client.get(f"/v1/jobs/{job.job_id}/documents?limit=1&cursor={cursor}", headers=headers_a)
        assert res_a_next.status_code == 200
        
def test_410_gone(store, fake_redis):
    job = store.create_crawl_job(
        "tenant_a",
        CrawlConfig(seed_urls=["http://x.com"], allowed_domains=["x.com"]),
        idempotency_key="key3",
        request_fingerprint="fp3"
    )
    # Set job status to done to set retention
    store.update(job.job_id, status=CrawlStatus.fetching_sitemap)
    store.update(job.job_id, status=CrawlStatus.crawling)
    store.update(job.job_id, status=CrawlStatus.extracting)
    store.update(job.job_id, status=CrawlStatus.classifying)
    store.update(job.job_id, status=CrawlStatus.done)
    
    # Mock expiration
    fake_redis.set(f"JOB:expired:{job.job_id}", "1")
    
    headers = {"X-Tenant-ID": "tenant_a", "Authorization": "Bearer dev-api-key-change-me", "X-Request-ID": "00000000-0000-4000-8000-000000000001"}
    res = client.get(f"/v1/jobs/{job.job_id}/documents", headers=headers)
    assert res.status_code == 410
