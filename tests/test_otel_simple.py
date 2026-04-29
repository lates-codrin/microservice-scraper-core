# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for OpenTelemetry integration."""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.services.otel import init_otel, init_instrumentors


def test_otel_disabled_by_default():
    """OpenTelemetry TracerProvider initialized but exporter disabled by default."""
    os.environ.pop("OTEL_ENABLED", None)
    
    # Should not raise, just initializes SDK
    init_otel("test-service")


def test_otel_initialization_enabled():
    """OpenTelemetry tries to initialize Jaeger when enabled."""
    os.environ["OTEL_ENABLED"] = "true"
    
    # Should not raise
    init_otel("test-service")


def test_init_instrumentors_calls_all_libraries():
    """init_instrumentors instruments FastAPI, httpx, SQLAlchemy, and Redis."""
    with patch("app.services.otel.FastAPIInstrumentor") as mock_fastapi:
        with patch("app.services.otel.HTTPXClientInstrumentor") as mock_httpx:
            with patch("app.services.otel.SQLAlchemyInstrumentor") as mock_sqlalchemy:
                with patch("app.services.otel.RedisInstrumentor") as mock_redis:
                    init_instrumentors()
                    
                    # Verify all instrumentors were called
                    mock_fastapi.instrument.assert_called_once()
                    mock_httpx.instrument.assert_called_once()
                    mock_sqlalchemy.instrument.assert_called_once()
                    mock_redis.instrument.assert_called_once()
