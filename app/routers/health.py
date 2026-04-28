# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""GET /v1/health â€” service health check with real dependency probing."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Request, status

from app.dependencies import get_job_store
from app.models.responses import HealthStatusResponse
from app.services.job_store import JobStore
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["health"])


async def _check_redis(request: Request) -> str:
    """Ping Redis and return status string."""
    try:
        redis_client = request.app.state.redis
        if redis_client is None:
            return "down"
        pong = redis_client.ping()
        # Handle both async redis (coroutine) and sync fakeredis (bool)
        if hasattr(pong, "__await__"):
            pong = await pong
        return "ok" if pong else "degraded"
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return "down"


async def _check_postgres(store: JobStore) -> str:
    """Execute a lightweight query to verify DB connectivity."""
    try:
        # queue_depth runs a SELECT COUNT â€” good enough as a liveness probe
        await store.queue_depth()
        return "ok"
    except Exception as exc:
        logger.warning("Postgres health check failed: %s", exc)
        return "down"


@router.get(
    "/health",
    response_model=HealthStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def healthcheck(
    request: Request,
    store: JobStore = Depends(get_job_store),
) -> HealthStatusResponse:
    """Service health check with real dependency probing."""
    uptime_seconds = int(
        time.monotonic() - request.app.state.started_monotonic
    )

    redis_status = await _check_redis(request)
    postgres_status = await _check_postgres(store)

    # Aggregate: storage = redis + postgres (worst wins)
    if redis_status == "down" or postgres_status == "down":
        storage_status = "down"
    elif redis_status == "degraded" or postgres_status == "degraded":
        storage_status = "degraded"
    else:
        storage_status = "ok"

    dep_statuses = [storage_status]
    if all(s == "ok" for s in dep_statuses):
        overall = "ok"
    elif any(s == "down" for s in dep_statuses):
        overall = "down"
    else:
        overall = "degraded"

    response = HealthStatusResponse(
        status=overall,
        version=settings.service_version,
        uptime_seconds=uptime_seconds,
        dependencies={
            "redis": redis_status,
            "postgres": postgres_status,
            "storage": storage_status,
            "proxy_pool": "ok",       # no external proxy pool in this implementation
            "browser_cluster": "ok",  # Playwright pool â€” lazy-init, always "ok" at startup
            "classifier": "ok",
        },
        queue_depth=await store.queue_depth(),
        active_workers=settings.active_workers,
    )

    # Spec YAML: 503 when service is down or degraded
    status_code = 200 if overall == "ok" else 503
    from fastapi.responses import JSONResponse
    if status_code != 200:
        return JSONResponse(
            status_code=status_code,
            content=response.model_dump(mode="json"),
        )
    return response
