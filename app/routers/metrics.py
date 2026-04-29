# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""GET /metrics Prometheus metrics exposition format."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.services.metrics import get_metrics

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
)
async def metrics() -> str:
    """Prometheus metrics exposition format. 
    
    Includes:
    - http_requests_total (method, status, endpoint)
    - http_request_duration_seconds (p50, p95, p99 quantiles)
    - vendor_cost_usd_total
    - vendor_tokens_total (input, output)
    - vendor_external_api_errors_total (dependency, error_type)
    - active_jobs (gauge)
    - documents_scraped_total
    """
    metrics_collector = get_metrics()
    return metrics_collector.render_prometheus()
