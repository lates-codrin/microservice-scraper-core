# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
POST /v1/admin/flush  ” dev-only: clear idempotency keys + cancel active jobs.

Guarded by DOCS_ENABLED=true (same flag that enables the Swagger UI).
Never expose in production (set DOCS_ENABLED=false).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.enums import CrawlStatus
from app.services.job_store import JobStore
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_ACTIVE_STATUSES = [
    CrawlStatus.queued.value,
    CrawlStatus.fetching_sitemap.value,
    CrawlStatus.crawling.value,
    CrawlStatus.extracting.value,
    CrawlStatus.classifying.value,
]


@router.post("/flush", status_code=status.HTTP_200_OK, include_in_schema=False)
async def flush_queue(
    request: Request,
    store: JobStore = Depends(get_job_store),
) -> JSONResponse:
    """
    Dev helper: cancel all active jobs for the current tenant and wipe
    their Redis idempotency keys so you can resubmit freely.

    Only available when DOCS_ENABLED=true.
    """
    if not settings.docs_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    tenant_id: str = request.state.tenant_id
    redis = store.redis

    # Cancel all active jobs for this tenant
    from datetime import UTC, datetime

    from sqlalchemy import select, update

    from app.models.db import DbCrawlJob

    stmt = select(DbCrawlJob).where(
        DbCrawlJob.tenant_id == tenant_id,
        DbCrawlJob.status.in_(_ACTIVE_STATUSES),
    )
    result = await store.session.execute(stmt)
    jobs = list(result.scalars().all())

    cancelled_ids = []
    for job in jobs:
        await store.session.execute(
            update(DbCrawlJob)
            .where(DbCrawlJob.job_id == job.job_id)
            .values(status=CrawlStatus.cancelled.value, completed_at=datetime.now(UTC))
        )
        cancelled_ids.append(job.job_id)

    await store.session.commit()

    # Wipe idempotency keys for this tenant from Redis
    pattern = f"IDEM:{tenant_id}:*"
    keys = redis.keys(pattern)
    fp_pattern = f"IDEM_FP:{tenant_id}:*"
    fp_keys = redis.keys(fp_pattern)
    all_keys = keys + fp_keys
    deleted_keys = len(all_keys)
    if all_keys:
        redis.delete(*all_keys)

    logger.warning(
        "admin/flush: tenant=%s cancelled %d jobs, deleted %d idem keys",
        tenant_id,
        len(cancelled_ids),
        deleted_keys,
    )

    return JSONResponse(
        content={
            "cancelled_jobs": cancelled_ids,
            "idempotency_keys_cleared": deleted_keys,
            "tenant_id": tenant_id,
        }
    )
