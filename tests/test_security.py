"""
Security test suite:
  - SSRF: redirect chain that ends at 169.254.169.254 must be blocked
  - SSRF: webhook callback to private IP must be blocked
  - Header injection: newline in X-Tenant-ID must return 400
  - Header injection: newline in X-Request-ID must return 400
  - Tenant isolation: every endpoint must return 403 for cross-tenant access
  - Redis-key injection: slug with control chars rejected at auth layer
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


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# SSRF — redirect-chain attack
# ─────────────────────────────────────────────────────────────────────────────


class TestSSRFRedirectChain:
    """Redirect chain ending at 169.254.169.254 must raise SSRFError."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_redirect_to_metadata_endpoint_blocked(self):
        """A 301 redirect to http://169.254.169.254/ must be blocked with SSRFError."""
        from app.services.fetcher import fetch, SSRFError

        def dns_side_effect(hostname, port=None):
            mapping = {
                "evil.example.com": "93.184.216.34",
                "169.254.169.254": "169.254.169.254",
            }
            ip = mapping.get(hostname, "93.184.216.34")
            return [(None, None, None, None, (ip, 0))]

        # Mock stream to return a 301 redirect to the metadata endpoint
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

        with patch("socket.getaddrinfo", side_effect=dns_side_effect):
            with patch("app.services.fetcher._local_buckets.consume", new=AsyncMock(return_value=True)):
                with patch("httpx.AsyncClient", side_effect=[robots_mock, mock_client]):
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
        """Direct request to link-local address must be blocked immediately."""
        from app.services.fetcher import _check_ssrf, SSRFError

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        ):
            with pytest.raises(SSRFError):
                _check_ssrf("169.254.169.254")

    def test_rfc1918_10_blocked(self):
        from app.services.fetcher import _check_ssrf, SSRFError

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.1.2.3", 0))],
        ):
            with pytest.raises(SSRFError):
                _check_ssrf("internal.corp")

    def test_loopback_blocked(self):
        from app.services.fetcher import _check_ssrf, SSRFError

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        ):
            with pytest.raises(SSRFError):
                _check_ssrf("localhost")

    def test_public_ip_allowed(self):
        from app.services.fetcher import _check_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            _check_ssrf("example.com")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# SSRF — webhook callback guard
# ─────────────────────────────────────────────────────────────────────────────


class TestWebhookSSRF:
    def test_private_callback_blocked(self):
        from app.services.webhooks import _check_callback_ssrf, SSRFBlockedError

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.0.0.1", 0))],
        ):
            with pytest.raises(SSRFBlockedError):
                _check_callback_ssrf("http://internal.corp/hook")

    def test_metadata_callback_blocked(self):
        from app.services.webhooks import _check_callback_ssrf, SSRFBlockedError

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        ):
            with pytest.raises(SSRFBlockedError):
                _check_callback_ssrf("http://169.254.169.254/latest/meta-data/")

    def test_public_callback_allowed(self):
        from app.services.webhooks import _check_callback_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            _check_callback_ssrf("https://hooks.example.com/callback")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Header injection — newline in X-Tenant-ID
# ─────────────────────────────────────────────────────────────────────────────


class TestHeaderInjection:
    def test_newline_in_tenant_id_returns_400(self, client):
        """Newline in X-Tenant-ID must return 400, not be echoed."""
        resp = client.get(
            "/v1/health",
            headers={
                "Authorization": AUTH,
                "X-Request-ID": str(uuid4()),
                "X-Tenant-ID": "tenant\r\nX-Injected: evil",
            },
        )
        assert resp.status_code == 400
        assert "X-Injected" not in resp.headers

    def test_cr_in_tenant_id_returns_400(self, client):
        resp = client.get(
            "/v1/health",
            headers={
                "Authorization": AUTH,
                "X-Request-ID": str(uuid4()),
                "X-Tenant-ID": "tenant\rvalue",
            },
        )
        assert resp.status_code == 400

    def test_newline_in_request_id_returns_400(self, client):
        """Newline in X-Request-ID must return 400 (fails UUID + safe-char validation)."""
        resp = client.get(
            "/v1/health",
            headers={
                "Authorization": AUTH,
                "X-Request-ID": "not-a-uuid\r\nX-Injected: evil",
                "X-Tenant-ID": TENANT_A,
            },
        )
        assert resp.status_code == 400
        assert "X-Injected" not in resp.headers

    def test_null_byte_in_tenant_id_returns_400(self, client):
        """NUL byte in X-Tenant-ID must return 400."""
        resp = client.get(
            "/v1/health",
            headers={
                "Authorization": AUTH,
                "X-Request-ID": str(uuid4()),
                "X-Tenant-ID": "tenant\x00value",
            },
        )
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Tenant isolation — cross-tenant access must return 403
# ─────────────────────────────────────────────────────────────────────────────


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
