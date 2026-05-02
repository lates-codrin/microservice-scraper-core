"""Integration test fixtures: TestClient, auth headers, canned content,
and fetch-layer mocking (extractor, classifier, and field_extractor run real)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings

# ---------------------------------------------------------------------------
# TestClient fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Fresh TestClient per test — exercises the full ASGI middleware stack."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Auth header helpers
# ---------------------------------------------------------------------------


def _auth_headers(
    request_id: str | None = None,
    tenant_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    """Compose a complete set of valid auth headers with sensible defaults."""
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "X-Request-ID": request_id or str(uuid.uuid4()),
        "X-Tenant-ID": tenant_id or settings.default_tenant_id,
        "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
    }
    return headers


# ---------------------------------------------------------------------------
# Canned HTML content — small, valid snippets the real extractor/classifier
# can process. Romanian municipal documents.
# ---------------------------------------------------------------------------

HTML_HCL = (
    b"<html><head><title>HCL 125/2024</title>"
    b'<link rel="canonical" href="https://primaria-exemplu.ro/hcl/125"/>'
    b"</head><body><article>"
    b"<h1>Hotarare nr. 125/2024 privind aprobarea bugetului local pe anul 2024</h1>"
    b"<p>Aceasta hotarare a fost adoptata de Consiliul Local in data de 15.03.2024.</p>"
    b"</article></body></html>"
)

HTML_BUGET = (
    b"<html><head><title>Buget Local 2024</title></head>"
    b"<body><article>"
    b"<h1>Buget local al municipiului pentru anul 2024</h1>"
    b"<p>Valoare totala: 125,000,000 lei</p>"
    b"</article></body></html>"
)

HTML_REGULAMENT = (
    b"<html><head><title>Regulament de organizare</title></head>"
    b"<body><article>"
    b"<h1>Regulament privind organizarea si functionarea aparatului de specialitate</h1>"
    b"</article></body></html>"
)

HTML_NO_MATCH = (
    b"<html><head><title>Notificare</title></head>"
    b"<body><p>Se aduce la cunostinta cetatenilor programul de audiente.</p></body></html>"
)


# ---------------------------------------------------------------------------
# Autouse fixture: mock only the outbound HTTP/Playwright layer.
# Extractor (trafilatura/pdfplumber), classifier, and field_extractor run real.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_fetch_success(monkeypatch):
    """Patch fetch and render_page so integration tests never hit real websites."""
    import app.services.scrape_service as svc
    from app.services.fetcher import FetchResult

    def _content_for_url(url: str) -> bytes:
        url_lower = url.lower()
        if "hcl" in url_lower or "/125" in url_lower:
            return HTML_HCL
        if "buget" in url_lower:
            return HTML_BUGET
        if "regulament" in url_lower:
            return HTML_REGULAMENT
        return HTML_NO_MATCH

    async def _mock_fetch(url, **kwargs):
        url_str = str(url)
        content = _content_for_url(url_str)
        return FetchResult(
            url=url_str,
            final_url=url_str,
            http_status=200,
            response_time_ms=37,
            redirect_chain=[],
            headers={"content-type": "text/html"},
            content=content,
            mime_type="text/html",
            warnings=[],
        )

    async def _mock_render(url, raw_html_bytes, render_mode, include_raw_html, timeout_ms):
        return raw_html_bytes, url, False

    monkeypatch.setattr(svc, "fetch", AsyncMock(side_effect=_mock_fetch))
    monkeypatch.setattr(svc, "render_page", AsyncMock(side_effect=_mock_render))
    return
