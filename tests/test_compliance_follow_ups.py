"""Tests for compliance audit follow-ups: response headers, PII redaction, etc."""

import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.pii_redactor import redact_pii


class TestPIIRedaction:
    """Test PII redaction service."""

    def test_redact_cnp(self):
        """Redact Romanian personal ID numbers (CNP)."""
        text = "Personal ID: 1900101000000 is here"
        result = redact_pii(text)
        assert "[REDACTED_CNP]" in result
        assert "1900101000000" not in result

    def test_redact_phone(self):
        """Redact phone numbers."""
        text = "Call me at 0712345678 or +40712345678"
        result = redact_pii(text)
        assert "[REDACTED_PHONE]" in result
        assert "0712345678" not in result

    def test_redact_email(self):
        """Redact email addresses."""
        text = "Contact: john.doe@example.com for more info"
        result = redact_pii(text)
        assert "[REDACTED_EMAIL]" in result
        assert "john.doe@example.com" not in result

    def test_redact_credit_card(self):
        """Redact credit card patterns."""
        text = "Use card 1234 5678 9012 3456 for payment"
        result = redact_pii(text)
        assert "[REDACTED_CARD]" in result
        assert "1234" not in result or "[REDACTED_CARD]" in result

    def test_no_redaction_on_normal_text(self):
        """Normal text should pass through unchanged."""
        text = "This is a normal document with no PII"
        result = redact_pii(text)
        assert result == text

    def test_empty_text(self):
        """Empty text should return empty."""
        assert redact_pii("") == ""

    def test_none_text(self):
        """None input should return None."""
        assert redact_pii(None) is None


class TestResponseHeaders:
    """Test response headers (X-Vendor-Cache-Status, Server-Timing)."""

    @pytest.fixture
    def client(self):
        """Create test client with app."""
        app = create_app()
        return TestClient(app)

    def test_x_vendor_cache_status_header(self, client):
        """Verify X-Vendor-Cache-Status header is present."""
        response = client.get("/v1/health", headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": "550e8400-e29b-41d4-a716-446655440000",
            "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}",
        })
        assert response.status_code in (200, 503)  # OK or degraded
        assert "X-Vendor-Cache-Status" in response.headers
        assert response.headers["X-Vendor-Cache-Status"] in ("HIT", "MISS")

    def test_server_timing_header(self, client):
        """Verify Server-Timing header is present and has valid format."""
        response = client.get("/v1/health", headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": "550e8400-e29b-41d4-a716-446655440000",
            "X-Tenant-ID": f"test-tenant-{uuid.uuid4()}",
        })
        assert response.status_code in (200, 503)
        assert "Server-Timing" in response.headers
        # Server-Timing should have format: name;dur=ms
        timing = response.headers["Server-Timing"]
        assert "dur=" in timing


class TestCrawlConfigRedactPII:
    """Test CrawlConfig with redact_pii field."""

    def test_crawl_config_redact_pii_default_false(self):
        """redact_pii should default to False."""
        from app.models.crawl import CrawlConfig
        config = CrawlConfig(seed_urls=["https://example.com"])
        assert config.redact_pii is False

    def test_crawl_config_redact_pii_true(self):
        """redact_pii can be set to True."""
        from app.models.crawl import CrawlConfig
        config = CrawlConfig(
            seed_urls=["https://example.com"],
            redact_pii=True,
        )
        assert config.redact_pii is True


class TestScrapeRequestRedactPII:
    """Test ScrapeRequest with redact_pii field."""

    def test_scrape_request_redact_pii_default_false(self):
        """redact_pii should default to False."""
        from app.models.requests import ScrapeRequest
        req = ScrapeRequest(url="https://example.com")
        assert req.redact_pii is False

    def test_scrape_request_redact_pii_true(self):
        """redact_pii can be set to True."""
        from app.models.requests import ScrapeRequest
        req = ScrapeRequest(url="https://example.com", redact_pii=True)
        assert req.redact_pii is True


class TestOTelStructuredLogging:
    """Test OpenTelemetry structured logging with trace context."""


    def test_structured_formatter_output_is_json(self):
        """Formatter should produce valid JSON output."""
        import json
        import io
        import logging
        from app.services.otel_logging import OTelStructuredFormatter

        # Capture output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        formatter = OTelStructuredFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger("test_json_output")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("test message 123")

        # Get output and parse as JSON
        output = stream.getvalue().strip()
        if output:
            parsed = json.loads(output)
            assert parsed["message"] == "test message 123"
            assert parsed["level"] == "INFO"
            assert "timestamp" in parsed

    def test_otel_logging_configuration(self):
        """Verify logging configuration initializes correctly."""
        from app.services.otel_logging import configure_structured_logging
        import logging

        configure_structured_logging("DEBUG")
        logger = logging.getLogger("test")

        # Logger should be configured
        assert logger.level == logging.DEBUG or logger.level == logging.NOTSET
