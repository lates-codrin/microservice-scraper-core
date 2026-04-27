from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request, status

from app.dependencies import get_job_store
from app.models.responses import HealthStatusResponse
from app.services.job_store import JobStore
from app.settings import settings

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthStatusResponse, status_code=status.HTTP_200_OK)
async def healthcheck(
    request: Request,
    store: JobStore = Depends(get_job_store),
) -> HealthStatusResponse:
    uptime_seconds = int(time.monotonic() - request.app.state.started_monotonic)
    return HealthStatusResponse(
        status="ok",
        version=settings.service_version,
        uptime_seconds=uptime_seconds,
        dependencies={
            "proxy_pool": "ok",
            "browser_cluster": "ok",
            "storage": "ok",
            "classifier": "ok",
        },
        queue_depth=await store.queue_depth(),
        active_workers=settings.active_workers,
    )