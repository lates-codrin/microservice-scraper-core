from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.dependencies import get_job_store
from app.main import app
from app.models.enums import ContentType, DocType
from app.models.document import ScrapedDocument
from app.services.extractor import ExtractionResult
from app.services.fetcher import FetchResult

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-api-key-change-me",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Tenant-ID": "test-tenant",
        "Idempotency-Key": str(uuid.uuid4()),
    }


def test_scrape_sync_fetches_extracts_and_persists(monkeypatch):
    store = AsyncMock()
    store.create_scrape_job.return_value = "sj_123"
    app.dependency_overrides[get_job_store] = lambda: store

    fetch_result = FetchResult(
        url="https://example.com/doc",
        final_url="https://example.com/doc",
        http_status=200,
        response_time_ms=37,
        redirect_chain=[],
        headers={"content-type": "text/html"},
        content=b"<html><body>Hotararea nr. 125 privind aprobarea bugetului local.</body></html>",
        mime_type="text/html",
        warnings=["fetch-warning"],
    )
    extraction_result = ExtractionResult(
        raw_text="Hotararea nr. 125 privind aprobarea bugetului local.",
        title="HCL 125/2024",
        canonical_url="https://example.com/doc",
        published_at=None,
        page_count=None,
        content_hash="sha256:testhash",
        content_length=52,
        language="ro",
        mime_type="text/html",
        warnings=["extract-warning"],
    )

    monkeypatch.setattr("app.routers.scrape.fetch", AsyncMock(return_value=fetch_result))
    monkeypatch.setattr(
        "app.routers.scrape.render_page",
        AsyncMock(return_value=(fetch_result.content, fetch_result.final_url, False)),
    )
    monkeypatch.setattr("app.routers.scrape.extract", lambda content, mime_type, source_url: extraction_result)
    monkeypatch.setattr(
        "app.routers.scrape.classify_document",
        lambda url, text: (DocType.hcl, 0.94, [{"doc_type": DocType.buget, "confidence": 0.3}]),
    )

    try:
        response = client.post(
            "/v1/scrape",
            json={
                "url": "https://example.com/doc",
                "render_javascript": "auto",
                "follow_redirects": True,
                "include_raw_html": True,
                "classify": True,
                "extract_structured": True,
                "timeout_ms": 30000,
                "mode": "sync",
            },
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["document"]["doc_type"] == "hcl"
        assert payload["document"]["title"] == "HCL 125/2024"
        assert payload["document"]["raw_text"] == extraction_result.raw_text
        assert payload["latency_ms"] == 37

        store.create_scrape_job.assert_awaited_once()
        store.add_document.assert_awaited_once()
        add_args = store.add_document.await_args.args
        assert add_args[0] == "sj_123"
        assert add_args[1] == "test-tenant"
        assert isinstance(add_args[2], ScrapedDocument)
        assert add_args[2].content_type == ContentType.html
        assert add_args[2].warnings == ["fetch-warning", "extract-warning"]
        assert store.update.await_count == 1
    finally:
        app.dependency_overrides.clear()