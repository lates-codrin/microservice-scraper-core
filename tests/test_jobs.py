"""
Tests for POST /v1/crawl, GET /v1/jobs/{job_id},
POST /v1/jobs/{job_id}/cancel, DELETE /v1/jobs/{job_id},
and idempotency-key collision.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT = settings.default_tenant_id
AUTH = f"Bearer {settings.api_key}"

CRAWL_PAYLOAD = {
    "config": {
        "seed_urls": ["https://primaria-exemplu.ro"],
        "allowed_domains": ["primaria-exemplu.ro"],
        "max_depth": 2,
        "max_pages": 50,
        "include_patterns": [],
        "exclude_patterns": [],
        "respect_robots_txt": True,
    }
}


def _headers(idempotency_key: str | None = None, request_id: str | None = None) -> dict:
    h = {
        "Authorization": AUTH,
        "X-Request-ID": request_id or str(uuid4()),
        "X-Tenant-ID": TENANT,
    }
    if idempotency_key is not None:
        h["Idempotency-Key"] = idempotency_key
    return h


@pytest.fixture()
def client():
    """Fresh TestClient with fresh app state per test."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _post_crawl(client, idempotency_key: str, payload: dict = CRAWL_PAYLOAD) -> tuple:
    """POST /v1/crawl. Returns (response, job_id | None)."""
    resp = client.post("/v1/crawl", json=payload, headers=_headers(idempotency_key))
    job_id = resp.json().get("job_id") if resp.status_code in (200, 202) else None
    return resp, job_id


# ---------------------------------------------------------------------------
# 1. Create job → returns 202 with job_id + queued status
# ---------------------------------------------------------------------------

def test_create_job_returns_202(client):
    ikey = str(uuid4())
    resp, job_id = _post_crawl(client, ikey)
    assert resp.status_code == 202, resp.text
    assert job_id is not None
    body = resp.json()
    assert body["status"] == "queued"
    assert "submitted_at" in body


# ---------------------------------------------------------------------------
# 2. Poll status — GET /v1/jobs/{job_id}
# ---------------------------------------------------------------------------

def test_get_job_returns_200_with_retry_after(client):
    ikey = str(uuid4())
    _, job_id = _post_crawl(client, ikey)
    assert job_id

    resp = client.get(f"/v1/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == job_id
    # Freshly created jobs are queued → Retry-After: 10
    assert body["status"] == "queued"
    assert resp.headers.get("Retry-After") == "10"


def test_get_unknown_job_returns_404(client):
    resp = client.get("/v1/jobs/cj_doesnotexist", headers=_headers())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# 3. Cancel — POST /v1/jobs/{job_id}/cancel
# ---------------------------------------------------------------------------

def test_cancel_job(client):
    ikey = str(uuid4())
    _, job_id = _post_crawl(client, ikey)
    assert job_id

    resp = client.post(f"/v1/jobs/{job_id}/cancel", headers=_headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["status"] == "cancelled"
    assert isinstance(body["documents_salvaged"], int)


def test_cancel_unknown_job_returns_404(client):
    resp = client.post("/v1/jobs/cj_nope/cancel", headers=_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Delete — DELETE /v1/jobs/{job_id}
# ---------------------------------------------------------------------------

def test_delete_job_returns_204(client):
    ikey = str(uuid4())
    _, job_id = _post_crawl(client, ikey)
    assert job_id

    resp = client.delete(f"/v1/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 204
    assert resp.content == b""  # no body


def test_delete_purges_job(client):
    ikey = str(uuid4())
    _, job_id = _post_crawl(client, ikey)

    client.delete(f"/v1/jobs/{job_id}", headers=_headers())
    # Subsequent GET must 404
    resp = client.get(f"/v1/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 404


def test_delete_unknown_job_returns_404(client):
    resp = client.delete("/v1/jobs/cj_ghost", headers=_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Full flow: create → poll → cancel → delete
# ---------------------------------------------------------------------------

def test_full_lifecycle(client):
    ikey = str(uuid4())

    # create
    resp, job_id = _post_crawl(client, ikey)
    assert resp.status_code == 202
    assert job_id

    # poll
    resp = client.get(f"/v1/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 200

    # cancel
    resp = client.post(f"/v1/jobs/{job_id}/cancel", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # delete
    resp = client.delete(f"/v1/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 204

    # gone
    resp = client.get(f"/v1/jobs/{job_id}", headers=_headers())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Idempotency — same key + same body → existing job (202 or 200)
# ---------------------------------------------------------------------------

def test_idempotency_same_key_same_body_returns_existing(client):
    ikey = str(uuid4())

    resp1, job_id1 = _post_crawl(client, ikey)
    assert resp1.status_code == 202

    resp2, job_id2 = _post_crawl(client, ikey)
    # second call is idempotent replay — server may return 200 or 202
    assert resp2.status_code in (200, 202), resp2.text
    assert job_id2 == job_id1


# ---------------------------------------------------------------------------
# 7. Idempotency — same key + different body → 409 duplicate_job
# ---------------------------------------------------------------------------

def test_idempotency_same_key_different_body_returns_409(client):
    ikey = str(uuid4())

    resp1, job_id1 = _post_crawl(client, ikey, payload=CRAWL_PAYLOAD)
    assert resp1.status_code == 202

    altered_payload = {
        "config": {
            "seed_urls": ["https://primaria-exemplu.ro"],
            "allowed_domains": ["primaria-exemplu.ro"],
            "max_pages": 9999,  # changed
        }
    }
    resp2 = client.post("/v1/crawl", json=altered_payload, headers=_headers(ikey))
    assert resp2.status_code == 409, resp2.text
    body = resp2.json()
    assert body["error"]["code"] == "duplicate_job"
    assert body["error"]["details"]["existing_job_id"] == job_id1


# ---------------------------------------------------------------------------
# 8. X-Request-ID echoed on error responses
# ---------------------------------------------------------------------------

def test_request_id_echoed_on_404(client):
    rid = str(uuid4())
    resp = client.get("/v1/jobs/cj_nope", headers=_headers(request_id=rid))
    assert resp.headers.get("X-Request-ID") == rid
