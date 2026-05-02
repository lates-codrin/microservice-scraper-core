from types import SimpleNamespace

import pytest

from app.crawl_runner import _persist_document


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class FakeAsyncRedisKnown:
    def __init__(self, known: set):
        self.known = set(known)
        self.added = set()

    async def sismember(self, key, member):
        return member in self.known

    async def sadd(self, key, member):
        self.added.add(member)


@pytest.mark.asyncio
async def test_persist_skips_known_hash():
    session = FakeSession()
    async_redis = FakeAsyncRedisKnown({"sha256:knownhash"})

    extraction = SimpleNamespace(
        raw_text="hello",
        canonical_url="https://example.com",
        title="t",
        language="ro",
        published_at=None,
        page_count=None,
        content_length=5,
        content_hash="sha256:knownhash",
        warnings=[],
    )

    doc = {
        "extraction": extraction,
        "mime_type": "text/html",
        "final_url": "https://example.com",
        "source_url": "https://example.com",
        "http_status": 200,
        "response_time_ms": 123,
        "redirect_chain": [],
        "used_playwright": False,
        "warnings": [],
        "raw_html": "<html></html>",
    }

    await _persist_document(
        session, "job_1", "tenant_x", doc, redact_pii=False, async_redis=async_redis
    )

    assert session.committed is False
    assert session.added == []


@pytest.mark.asyncio
async def test_persist_saves_and_adds_hash():
    session = FakeSession()
    async_redis = FakeAsyncRedisKnown(set())

    extraction = SimpleNamespace(
        raw_text="hello",
        canonical_url="https://example.com",
        title="t",
        language="ro",
        published_at=None,
        page_count=None,
        content_length=5,
        content_hash="sha256:newhash",
        warnings=[],
    )

    doc = {
        "extraction": extraction,
        "mime_type": "text/html",
        "final_url": "https://example.com",
        "source_url": "https://example.com",
        "http_status": 200,
        "response_time_ms": 123,
        "redirect_chain": [],
        "used_playwright": False,
        "warnings": [],
        "raw_html": "<html></html>",
    }

    await _persist_document(
        session, "job_2", "tenant_x", doc, redact_pii=False, async_redis=async_redis
    )

    assert session.committed is True
    assert len(session.added) == 1
    # fake redis should have recorded the added hash
    assert "sha256:newhash" in async_redis.added
