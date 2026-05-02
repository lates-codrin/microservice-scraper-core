# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
Security test suite:
  - SSRF: redirect chain that ends at 169.254.169.254 must be blocked
  - SSRF: webhook callback to private IP must be blocked
  - Header injection: newline in X-Tenant-ID must return 400
  - Tenant isolation: every endpoint must return 403 for cross-tenant access
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings

AUTH = f"Bearer {settings.api_key}"
TENANT_A = "tenant-alpha"
TENANT_B = "tenant-beta"


def _h(tenant: str = TENANT_A, rid: str | None = None, ikey: str | None = None) -> dict:
    h = {
        "Authorization": AUTH,
        "X-Request-ID": rid or str(uuid4()),
        "X-Tenant-ID": tenant,
    }
    if ikey:
        h["Idempotency-Key"] = ikey
    return h


CRAWL_PAYLOAD = {
    "config": {
        "seed_urls": ["https://primaria-exemplu.ro"],
        "allowed_domains": ["primaria-exemplu.ro"],
    }
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SSRF ” redirect-chain attack
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSSRFRedirectChain:
    """Redirect chain ending at 169.254.169.254 must raise SSRFError."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_redirect_to_metadata_endpoint_blocked(self):
        """A 301 redirect to http://169.254.169.254/ must be blocked with SSRFError."""
        from app.services.fetcher import SSRFError, fetch

        def dns_side_effect(hostname, port=None):
            mapping = {
                "evil.example.com": "93.184.216.34",
                "169.254.169.254": "169.254.169.254",
            }
            ip = mapping.get(hostname, "93.184.216.34")
            return [(None, None, None, None, (ip, 0))]

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.status_code = 301
        mock_stream_ctx.headers = {
            "location": "http://169.254.169.254/latest/meta-data/",
            "content-type": "text/html",
        }
        mock_stream_ctx.history = []
        mock_stream_ctx.url = "https://evil.example.com/"
        mock_stream_ctx.aread = AsyncMock(return_value=b"")

        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        robots_mock = AsyncMock()
        robots_resp = MagicMock()
        robots_resp.status_code = 404
        robots_resp.text = ""
        robots_mock.get = AsyncMock(return_value=robots_resp)
        robots_mock.__aenter__ = AsyncMock(return_value=robots_mock)
        robots_mock.__aexit__ = AsyncMock(return_value=False)

        with patch("socket.getaddrinfo", side_effect=dns_side_effect), patch(
            "app.services.fetcher._local_buckets.consume", new=AsyncMock(return_value=True)
        ), patch("httpx.AsyncClient", side_effect=[robots_mock, mock_client]):
            with pytest.raises(SSRFError) as exc_info:
                self._run(
                    fetch(
                        "https://evil.example.com/",
                        respect_robots_txt=False,
                        redis=None,
                    )
                )
        assert "169.254.169.254" in str(exc_info.value)

    def test_direct_link_local_blocked(self):
        from app.services.fetcher import SSRFError, _check_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        ), pytest.raises(SSRFError):
            _check_ssrf("169.254.169.254")

    def test_rfc1918_10_blocked(self):
        from app.services.fetcher import SSRFError, _check_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.1.2.3", 0))],
        ), pytest.raises(SSRFError):
            _check_ssrf("internal.corp")

    def test_loopback_blocked(self):
        from app.services.fetcher import SSRFError, _check_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        ), pytest.raises(SSRFError):
            _check_ssrf("localhost")

    def test_public_ip_allowed(self):
        from app.services.fetcher import _check_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            _check_ssrf("example.com")  # must not raise


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SSRF ” webhook callback guard
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestWebhookSSRF:
    def test_private_callback_blocked(self):
        from app.services.webhooks import SSRFBlockedError, _check_callback_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.0.0.1", 0))],
        ), pytest.raises(SSRFBlockedError):
            _check_callback_ssrf("http://internal.corp/hook")

    def test_metadata_callback_blocked(self):
        from app.services.webhooks import SSRFBlockedError, _check_callback_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        ), pytest.raises(SSRFBlockedError):
            _check_callback_ssrf("http://169.254.169.254/latest/meta-data/")

    def test_public_callback_allowed(self):
        from app.services.webhooks import _check_callback_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            _check_callback_ssrf("https://hooks.example.com/callback")  # must not raise


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Header injection ” test the middleware validation directly
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHeaderInjection:
    """Test that _SAFE_SLUG_RE rejects control chars.

    Note: httpx TestClient silently strips \\r\\n from header values before
    they reach the server, so we test the regex directly instead.
    """

    def test_safe_slug_rejects_newline(self):
        from app.middleware.auth_headers import _SAFE_SLUG_RE

        assert _SAFE_SLUG_RE.match("tenant\r\nX-Injected: evil") is None

    def test_safe_slug_rejects_cr(self):
        from app.middleware.auth_headers import _SAFE_SLUG_RE

        assert _SAFE_SLUG_RE.match("tenant\rvalue") is None

    def test_safe_slug_rejects_null(self):
        from app.middleware.auth_headers import _SAFE_SLUG_RE

        assert _SAFE_SLUG_RE.match("tenant\x00value") is None

    def test_safe_slug_accepts_normal(self):
        from app.middleware.auth_headers import _SAFE_SLUG_RE

        assert _SAFE_SLUG_RE.match("ph-balta-doamnei") is not None

    def test_safe_slug_accepts_uuid(self):
        from app.middleware.auth_headers import _SAFE_SLUG_RE

        assert _SAFE_SLUG_RE.match(str(uuid4())) is not None

    def test_header_injection_request_id_returns_400(self, client):
        resp = client.get(
            "/v1/health",
            headers={"X-Request-ID": "123\nInject: true", "X-Tenant-ID": "test-tenant"},
        )
        assert resp.status_code == 400

    def test_header_injection_tenant_id_returns_400(self, client):
        resp = client.get(
            "/v1/health",
            headers={"X-Request-ID": str(uuid4()), "X-Tenant-ID": "test\nInject: true"},
        )
        assert resp.status_code == 400


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tenant isolation ” cross-tenant access must return 403
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTenantIsolation:
    """Every job endpoint must 403 when a different tenant tries to access."""

    def _create_job(self, client) -> str:
        resp = client.post(
            "/v1/crawl",
            json=CRAWL_PAYLOAD,
            headers=_h(TENANT_A, ikey=str(uuid4())),
        )
        assert resp.status_code == 202, resp.text
        return resp.json()["job_id"]

    def test_cross_tenant_get_job_returns_403(self, client):
        job_id = self._create_job(client)
        resp = client.get(f"/v1/jobs/{job_id}", headers=_h(TENANT_B))
        assert resp.status_code == 403

    def test_cross_tenant_get_documents_returns_403(self, client):
        job_id = self._create_job(client)
        resp = client.get(f"/v1/jobs/{job_id}/documents", headers=_h(TENANT_B))
        assert resp.status_code == 403

    def test_cross_tenant_cancel_returns_403(self, client):
        job_id = self._create_job(client)
        resp = client.post(f"/v1/jobs/{job_id}/cancel", headers=_h(TENANT_B))
        assert resp.status_code == 403

    def test_cross_tenant_delete_returns_403(self, client):
        job_id = self._create_job(client)
        resp = client.delete(f"/v1/jobs/{job_id}", headers=_h(TENANT_B))
        assert resp.status_code == 403

    def test_tenant_a_can_access_own_job(self, client):
        job_id = self._create_job(client)
        resp = client.get(f"/v1/jobs/{job_id}", headers=_h(TENANT_A))
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == TENANT_A
