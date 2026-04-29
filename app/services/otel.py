# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""OpenTelemetry initialization and setup."""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

logger = logging.getLogger(__name__)


def init_otel(service_name: str) -> None:
    """Initialize OpenTelemetry tracing infrastructure.
    
    Sets up TracerProvider with optional Jaeger exporter if OTEL_ENABLED=true.
    Reads config from environment variables:
    - OTEL_ENABLED: Enable OTel (default: false)
    - JAEGER_HOST: Jaeger agent host (default: localhost)
    - JAEGER_PORT: Jaeger agent port (default: 6831)
    
    Args:
        service_name: Service name for traces
    """
    otel_enabled = os.getenv("OTEL_ENABLED", "false").lower() in ("true", "1", "yes")

    # Create base TracerProvider
    trace_provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: service_name})
    )
    trace.set_tracer_provider(trace_provider)
    logger.info("OpenTelemetry SDK initialized: service=%s", service_name)

    if not otel_enabled:
        logger.info("OTel exporter disabled (OTEL_ENABLED=false)")
        return

    # Optionally add Jaeger exporter if enabled
    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        
        jaeger_host = os.getenv("JAEGER_HOST", "localhost")
        jaeger_port = int(os.getenv("JAEGER_PORT", "6831"))
        
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_host,
            agent_port=jaeger_port,
        )
        trace_provider.add_span_processor(SimpleSpanProcessor(jaeger_exporter))
        
        logger.info(
            "Jaeger exporter initialized: %s:%d",
            jaeger_host,
            jaeger_port,
        )
    except ImportError:
        logger.info("Jaeger exporter not installed, skipping")
    except Exception as exc:
        logger.warning("Jaeger exporter initialization failed: %s", exc)


def init_instrumentors() -> None:
    """Initialize OpenTelemetry auto-instrumentation for common libraries."""
    try:
        # FastAPI request/response tracing
        FastAPIInstrumentor.instrument()
        logger.info("OpenTelemetry: FastAPI instrumented")

        # HTTP client tracing (httpx used for scraping)
        HTTPXClientInstrumentor.instrument()
        logger.info("OpenTelemetry: httpx instrumented")

        # Database query tracing
        SQLAlchemyInstrumentor.instrument()
        logger.info("OpenTelemetry: SQLAlchemy instrumented")

        # Redis command tracing
        RedisInstrumentor.instrument()
        logger.info("OpenTelemetry: Redis instrumented")

    except Exception as exc:
        logger.warning("OpenTelemetry instrumentation failed: %s", exc)
