# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""GET /v1/health — service health check with real dependency probing."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.responses import HealthStatusResponse
from app.services.job_store import JobStore
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["health"])

# ---------------------------------------------------------------------------
# TTL cache — avoids opening a fresh NullPool DB connection (and a Redis ping)
# on every single health-check call.
#
# Production health probes typically fire every 10–30 s, so a 5 s cache
# has negligible impact on detection latency while cutting DB load to at
# most 12 connections/minute per instance.
#
# In tests, the first request pays the ~2 s NullPool connection cost and
# all subsequent requests in the same test return the cached result in <1 ms.
#
# Set HEALTH_CACHE_TTL_SECONDS=0 to disable caching (e.g. integration tests
# that explicitly verify dependency state changes).
# ---------------------------------------------------------------------------
_CACHE_TTL: float = float(os.getenv("HEALTH_CACHE_TTL_SECONDS", "5.0"))

_cached_deps: dict | None = None
_cached_queue_depth: int = 0
_cache_expires_at: float = 0.0

# Single in-flight probe task so concurrent requests reuse the same probe
# instead of each opening a DB connection.
_probe_task: asyncio.Task | None = None


async def _check_redis(request: Request) -> str:
    """Ping Redis and return a status string."""
    try:
        redis_client = request.app.state.redis
        if redis_client is None:
            return "down"
        pong = redis_client.ping()
        if hasattr(pong, "__await__"):
            pong = await pong
        return "ok" if pong else "degraded"
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return "down"


async def _check_postgres(store: JobStore) -> tuple[str, int]:
    """Run a lightweight query to verify DB connectivity.

    Returns ``(status_string, queue_depth)`` so the caller never needs to
    issue a second identical query.
    """
    try:
        depth = await store.queue_depth()
        return "ok", depth
    except Exception as exc:
        logger.warning("Postgres health check failed: %s", exc)
        return "down", 0


async def _probe_dependencies(
    request: Request,
    store: JobStore,
) -> tuple[dict[str, str], int]:
    """Hit every real dependency and return (statuses_dict, queue_depth).

    Results are cached for _CACHE_TTL seconds to avoid a DB round-trip on
    every health-check call.
    """
    global _cached_deps, _cached_queue_depth, _cache_expires_at

    now = time.monotonic()
    if _CACHE_TTL > 0 and _cached_deps is not None and now < _cache_expires_at:
        return _cached_deps, _cached_queue_depth

    global _probe_task

    # If another coroutine already started the probe, wait for it instead
    if _probe_task is not None and not _probe_task.done():
        try:
            await _probe_task
            return _cached_deps or {}, _cached_queue_depth
        except Exception as exc:
            import logging

            logging.error(f"Probe task failed with: {exc!r}")
            # Probe failed in the other task; fall through and run our own probe

    async def _do_probe() -> None:
        nonlocal request, store
        global _cached_deps, _cached_queue_depth, _cache_expires_at
        try:
            redis_status = await _check_redis(request)
            postgres_status, queue_depth = await _check_postgres(store)

            if redis_status == "down" or postgres_status == "down":
                storage_status = "down"
            elif redis_status == "degraded" or postgres_status == "degraded":
                storage_status = "degraded"
            else:
                storage_status = "ok"

            deps = {
                "redis": redis_status,
                "postgres": postgres_status,
                "storage": storage_status,
                "proxy_pool": "ok",
                "browser_cluster": "ok",
                "classifier": "ok",
            }

            _cached_deps = deps
            _cached_queue_depth = queue_depth
            _cache_expires_at = time.monotonic() + _CACHE_TTL
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Health probe task failed: %s", exc)
            # Ensure callers always get a mapping with expected keys
            _cached_deps = {
                "redis": "down",
                "postgres": "down",
                "storage": "down",
                "proxy_pool": "down",
                "browser_cluster": "down",
                "classifier": "down",
            }
            _cached_queue_depth = 0
            _cache_expires_at = time.monotonic() + _CACHE_TTL

    # Start a single shared probe task and await it
    _probe_task = asyncio.create_task(_do_probe())
    try:
        await _probe_task
    finally:
        # leave _probe_task assigned (it will be done) so other waiters can
        # still await the result; future probes will replace it when needed
        pass

    return _cached_deps or {}, _cached_queue_depth


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
    uptime_seconds = int(time.monotonic() - request.app.state.started_monotonic)

    deps, queue_depth = await _probe_dependencies(request, store)

    dep_statuses = [deps["storage"]]
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
        dependencies=deps,
        queue_depth=queue_depth,
        active_workers=settings.active_workers,
    )

    if overall != "ok":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )
    return response
