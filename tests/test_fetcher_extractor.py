"""
Tests for app/services/fetcher.py and app/services/extractor.py.

Covers:
 - Rate-limit token bucket (in-process)
 - robots.txt blocking
 - SSRF rejection (private IP, loopback, link-local)
 - Diacritic round-trip (ș U+0219 / Timișoara, Hotărârea)
 - PDF page count
 - OCR fallback warning
 - Password-protected PDF warning
"""
from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


# ============================================================================
# FETCHER TESTS
# ============================================================================


class TestRateLimitTokenBucket:
    """In-process token bucket drains and recovers."""

    def setup_method(self):
        from app.services.fetcher import _InProcessTokenBucket
        self.bucket = _InProcessTokenBucket()

    def test_first_request_allowed(self):
        allowed = _run(self.bucket.consume("example.com", rate=1.0))
        assert allowed is True

    def test_second_immediate_request_blocked(self):
        _run(self.bucket.consume("example.com", rate=1.0))  # drains bucket
        allowed = _run(self.bucket.consume("example.com", rate=1.0))
        assert allowed is False

    def test_different_domains_independent(self):
        _run(self.bucket.consume("alpha.ro", rate=1.0))
        _run(self.bucket.consume("alpha.ro", rate=1.0))  # drains alpha
        # beta still has tokens
        allowed = _run(self.bucket.consume("beta.ro", rate=1.0))
        assert allowed is True

    def test_high_rate_allows_multiple(self):
        """rate=5 → 5 tokens; first 5 calls succeed."""
        results = [_run(self.bucket.consume("fast.ro", rate=5.0)) for _ in range(5)]
        assert all(results)
        sixth = _run(self.bucket.consume("fast.ro", rate=5.0))
        assert sixth is False


class TestSSRFRejection:
    """_check_ssrf raises SSRFError for private/loopback/link-local IPs."""

    def _check(self, hostname):
        from app.services.fetcher import _check_ssrf
        _check_ssrf(hostname)

    def test_loopback_ipv4(self):
        from app.services.fetcher import SSRFError
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            with pytest.raises(SSRFError):
                self._check("localhost")

    def test_rfc1918_10(self):
        from app.services.fetcher import SSRFError
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 0))]):
            with pytest.raises(SSRFError):
                self._check("internal.host")

    def test_rfc1918_172(self):
        from app.services.fetcher import SSRFError
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("172.16.5.5", 0))]):
            with pytest.raises(SSRFError):
                self._check("docker.internal")

    def test_rfc1918_192(self):
        from app.services.fetcher import SSRFError
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("192.168.1.1", 0))]):
            with pytest.raises(SSRFError):
                self._check("router.local")

    def test_link_local(self):
        from app.services.fetcher import SSRFError
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("169.254.169.254", 0))]):
            with pytest.raises(SSRFError):
                self._check("metadata.google.internal")

    def test_public_ip_allowed(self):
        """Public IP must not raise."""
        from app.services.fetcher import _check_ssrf
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
            _check_ssrf("example.com")  # should not raise


class TestRobotsBlocking:
    """fetch() raises RobotsDisallowedError when robots.txt blocks the URL."""

    def test_robots_blocks_url(self):
        from app.services.fetcher import fetch, RobotsDisallowedError

        disallow_all = "User-agent: *\nDisallow: /"

        # Patch socket.getaddrinfo to return a public address
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
            # Patch _InProcessTokenBucket.consume to always allow
            with patch("app.services.fetcher._local_buckets.consume", new=AsyncMock(return_value=True)):
                # Patch httpx.AsyncClient
                mock_robots_resp = MagicMock()
                mock_robots_resp.status_code = 200
                mock_robots_resp.text = disallow_all

                async def mock_get(url, **kwargs):
                    return mock_robots_resp

                mock_client = AsyncMock()
                mock_client.get = mock_get
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)

                with patch("httpx.AsyncClient", return_value=mock_client):
                    with pytest.raises(RobotsDisallowedError):
                        _run(fetch(
                            "https://example.com/secret",
                            respect_robots_txt=True,
                            redis=None,
                        ))

    def test_robots_disabled_skips_check(self):
        """respect_robots_txt=False → no robots.txt fetch."""
        from app.services.fetcher import fetch

        disallow_all = "User-agent: *\nDisallow: /"

        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
            with patch("app.services.fetcher._local_buckets.consume", new=AsyncMock(return_value=True)):

                # Build a mock streaming response
                mock_stream_ctx = AsyncMock()
                mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
                mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_stream_ctx.status_code = 200
                mock_stream_ctx.headers = {"content-type": "text/html"}
                mock_stream_ctx.history = []
                mock_stream_ctx.url = "https://example.com/"

                async def _iter_bytes():
                    yield b"<html>ok</html>"

                mock_stream_ctx.aiter_bytes = _iter_bytes

                mock_client = MagicMock()
                mock_client.stream = MagicMock(return_value=mock_stream_ctx)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)

                with patch("httpx.AsyncClient", return_value=mock_client):
                    result = _run(fetch(
                        "https://example.com/",
                        respect_robots_txt=False,
                        redis=None,
                    ))
                assert result.http_status == 200


# ============================================================================
# EXTRACTOR TESTS
# ============================================================================


class TestDiacriticRoundTrip:
    """Romanian diacritics must survive extraction unchanged."""

    def test_hotararea(self):
        from app.services.extractor import _assert_romanian_diacritics
        original = "Hotărârea privind bugetul"
        result = _assert_romanian_diacritics(original)
        assert result == original

    def test_timisoara_comma_below(self):
        from app.services.extractor import _assert_romanian_diacritics
        # ș = U+0219 comma-below, NOT ş = U+015F cedilla
        original = "Timi\u0219oara"
        result = _assert_romanian_diacritics(original)
        assert result == original
        assert "\u015f" not in result  # no cedilla

    def test_cedilla_corrected_to_comma_below(self):
        from app.services.extractor import _assert_romanian_diacritics
        # Input uses wrong cedilla-ş, output must be comma-below-ș
        wrong = "Timi\u015foara"
        corrected = _assert_romanian_diacritics(wrong)
        assert "\u0219" in corrected  # ș (comma-below) present
        assert "\u015f" not in corrected  # ş (cedilla) removed

    def test_all_special_chars(self):
        from app.services.extractor import _assert_romanian_diacritics
        sample = "ă â î ș ț Ș Ț"
        result = _assert_romanian_diacritics(sample)
        # comma-below chars must be preserved, cedilla must not appear
        assert "ș" in result
        assert "ț" in result


class TestPDFExtraction:
    """PDF extraction: page count, OCR fallback, password protection."""

    def _make_pdf_with_text(self, text: str) -> bytes:
        """Create a minimal in-memory PDF using fpdf2 if available, else use a fixture."""
        try:
            from fpdf import FPDF  # type: ignore[import-untyped]
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            pdf.cell(text=text)
            return pdf.output()
        except ImportError:
            return b""  # will be skipped

    def test_page_count_extracted(self):
        """pdfplumber must report correct page_count."""
        try:
            import pdfplumber  # noqa: F401
        except ImportError:
            pytest.skip("pdfplumber not installed")

        try:
            from fpdf import FPDF  # type: ignore
            pdf = FPDF()
            pdf.add_page()
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            pdf.cell(text="page one")
            pdf_bytes = pdf.output()
        except ImportError:
            pytest.skip("fpdf2 not installed for PDF generation")

        from app.services.extractor import _extract_pdf
        result = _extract_pdf(pdf_bytes)
        assert result.page_count == 2

    def test_ocr_fallback_warning_on_empty_text(self):
        """Empty text layer triggers ocr_fallback_used warning."""
        from app.services import extractor

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_page.to_image.return_value = MagicMock(original=MagicMock())

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        try:
            import pytesseract  # noqa: F401 — guard
        except ImportError:
            pytest.skip("pytesseract not installed")

        with patch("app.services.extractor.pdfplumber") as mock_pdfplumber, \
             patch("app.services.extractor.pytesseract") as mock_tess:
            mock_pdfplumber.open.return_value = mock_pdf
            mock_tess.image_to_string.return_value = "ocr text"
            result = extractor._extract_pdf(b"%PDF-fake")

        assert "ocr_fallback_used" in result.warnings

    def test_password_protected_pdf_warning(self):
        """Encrypted PDF emits pdf_password_protected and returns empty text."""
        from app.services import extractor

        with patch("app.services.extractor.pdfplumber") as mock_pdfplumber:
            mock_pdfplumber.open.side_effect = Exception("password required")
            result = extractor._extract_pdf(b"%PDF-encrypted")

        assert "pdf_password_protected" in result.warnings
        assert result.raw_text == ""

    def test_content_hash_format(self):
        """content_hash must start with 'sha256:'."""
        from app.services.extractor import _extract_html
        result = _extract_html(b"<html><body>test</body></html>")
        assert result.content_hash.startswith("sha256:")

    def test_content_length_matches_raw_text(self):
        """content_length must equal len(raw_text)."""
        from app.services.extractor import _extract_html
        result = _extract_html(b"<html><body>Hello World</body></html>")
        assert result.content_length == len(result.raw_text)

    def test_language_always_ro(self):
        from app.services.extractor import _extract_html, _extract_pdf
        html_result = _extract_html(b"<html><body>text</body></html>")
        assert html_result.language == "ro"


class TestHTMLExtraction:
    """HTML extraction metadata."""

    def test_title_extracted(self):
        try:
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        from app.services.extractor import _extract_html
        html = b"<html><head><title>HCL 125/2024</title></head><body><p>text</p></body></html>"
        result = _extract_html(html)
        assert result.title == "HCL 125/2024"

    def test_canonical_url_extracted(self):
        try:
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        from app.services.extractor import _extract_html
        html = (
            b'<html><head>'
            b'<link rel="canonical" href="https://exemplu.ro/hcl/125"/>'
            b'</head><body><p>text</p></body></html>'
        )
        result = _extract_html(html)
        assert result.canonical_url == "https://exemplu.ro/hcl/125"

    def test_published_at_from_time_tag(self):
        try:
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        from app.services.extractor import _extract_html
        html = b'<html><body><time datetime="2024-04-22T10:00:00">22 Apr 2024</time></body></html>'
        result = _extract_html(html)
        assert result.published_at == "2024-04-22"
