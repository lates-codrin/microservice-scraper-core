# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""GET /metrics Prometheus metrics exposition format."""

from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import PlainTextResponse

from app.services.metrics import get_metrics

router = APIRouter(prefix="/v1", tags=["health"])


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics exposition",
    description="Prometheus-format metrics for scraping. Includes http_requests_total, http_request_duration_seconds, vendor_cost_usd_total, vendor_tokens_total, vendor_external_api_errors_total, active_jobs, documents_scraped_total.",
)
async def metrics(
    x_request_id: str = Header(..., alias="X-Request-ID"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> str:
    """Prometheus metrics exposition format in text/plain.

    Requires:
    - X-Request-ID: UUID for request tracing
    - X-Tenant-ID: Tenant identifier

    Returns metrics with labels for method, status, endpoint, dependency, error_type.
    """
    metrics_collector = get_metrics()
    return metrics_collector.render_prometheus()
