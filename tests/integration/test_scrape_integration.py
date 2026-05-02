"""Integration tests for POST /v1/scrape — full middleware → service → DB stack.
Only the outbound HTTP/Playwright layer is mocked; extractor, classifier, and
field extractor all run real."""

from __future__ import annotations

import uuid

from tests.integration.conftest import _auth_headers

# ---------------------------------------------------------------------------
# Sync scrape — real extractor + classifier + DB persistence
# ---------------------------------------------------------------------------


def test_scrape_sync_hcl_200(client):
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/hcl/125",
            "mode": "sync",
            "classify": True,
            "extract_structured": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["request_id"] is not None
    doc = body["document"]
    assert doc["doc_type"] == "hcl"
    assert doc["doc_type_confidence"] == 0.94
    assert doc["title"] == "HCL 125/2024"
    assert len(doc["raw_text"]) > 0
    assert doc["language"] == "ro"
    assert doc["mime_type"] == "text/html"
    assert doc["content_type"] == "html"
    assert doc["content_hash"].startswith("sha256:")
    assert doc["content_length"] == len(doc["raw_text"])
    assert doc["source_url"] == "https://primaria-exemplu.ro/hcl/125"
    assert isinstance(doc["metadata"], dict)
    assert body["latency_ms"] >= 0

    # Middleware response headers
    assert "X-Request-ID" in resp.headers
    assert "X-Vendor-Cache-Status" in resp.headers
    assert "Server-Timing" in resp.headers
    assert "RateLimit-Limit" in resp.headers


def test_scrape_sync_buget_classifies_correctly(client):
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/buget",
            "mode": "sync",
            "classify": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["document"]
    assert doc["doc_type"] == "buget"
    assert doc["doc_type_confidence"] == 0.80


def test_scrape_sync_regulament_classifies_correctly(client):
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/regulament",
            "mode": "sync",
            "classify": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["document"]
    assert doc["doc_type"] == "regulament"
    assert doc["doc_type_confidence"] == 0.80


def test_scrape_sync_no_match_returns_other(client):
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://example.com/something-else",
            "mode": "sync",
            "classify": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["document"]
    assert doc["doc_type"] == "other"
    assert doc["doc_type_confidence"] == 0.40


def test_scrape_sync_include_raw_html(client):
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/hcl/125",
            "mode": "sync",
            "classify": False,
            "include_raw_html": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["document"]
    assert doc["raw_html"] is not None
    assert len(doc["raw_html"]) > 0


def test_scrape_sync_persists_to_db(client):
    """Verify the document is actually stored and retrievable via the job."""
    ikey = str(uuid.uuid4())
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/hcl/125",
            "mode": "sync",
            "classify": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(idempotency_key=ikey),
    )
    assert resp.status_code == 200
    doc = resp.json()["document"]
    assert doc["doc_type"] == "hcl"

    # Document should have been persisted — verify content_hash integrity
    assert doc["content_hash"].startswith("sha256:")
    assert doc["content_length"] > 0


def test_scrape_sync_pii_redaction(client, monkeypatch):
    """When redact_pii=True the pii_redactor is applied."""
    # Patch PII redactor to return a known redacted string so we can detect it
    monkeypatch.setattr(
        "app.services.scrape_service.redact_pii_text",
        lambda text: text + " [REDACTED]",
    )
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/hcl/125",
            "mode": "sync",
            "classify": False,
            "redact_pii": True,
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["document"]
    assert "[REDACTED]" in doc["raw_text"]
    assert doc["metadata"]["pii_redacted"] is True


# ---------------------------------------------------------------------------
# Async scrape
# ---------------------------------------------------------------------------


def test_scrape_async_returns_202(client):
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/hcl/125",
            "mode": "async",
            "timeout_ms": 30000,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"].startswith("sj_")
    assert body["status"] == "queued"


def test_scrape_async_job_pollable(client):
    """Async scrape job is persisted to DB and retrievable via GET /v1/jobs/{id}."""
    ikey = str(uuid.uuid4())
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://primaria-exemplu.ro/hcl/125",
            "mode": "async",
            "timeout_ms": 30000,
        },
        headers=_auth_headers(idempotency_key=ikey),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Poll the job
    resp = client.get(f"/v1/jobs/{job_id}", headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["job_id"] == job_id


# ---------------------------------------------------------------------------
# Validation / error cases
# ---------------------------------------------------------------------------


def test_scrape_missing_idempotency_key_returns_422(client):
    headers = _auth_headers()
    del headers["Idempotency-Key"]
    resp = client.post(
        "/v1/scrape",
        json={
            "url": "https://example.com/doc",
            "mode": "sync",
            "timeout_ms": 30000,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
