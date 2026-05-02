# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Background worker entry point for async scrape jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import redis as redis_lib
import redis.asyncio as aioredis
from sqlalchemy import select, update

from app.constants import JOB_ID_PREFIX_SCRAPE
from app.db import async_session_maker
from app.models.db import DbCrawlJob
from app.models.enums import CrawlStatus
from app.services.job_store import JobStore
from app.services.scrape_service import execute_sync_scrape
from app.settings import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2


async def _claim_queued_scrape_job(session) -> DbCrawlJob | None:
    stmt = (
        select(DbCrawlJob)
        .where(DbCrawlJob.status == CrawlStatus.queued.value)
        .where(DbCrawlJob.job_id.like(f"{JOB_ID_PREFIX_SCRAPE}%"))
        .order_by(DbCrawlJob.submitted_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None

    await session.execute(
        update(DbCrawlJob)
        .where(DbCrawlJob.job_id == job.job_id)
        .values(
            status=CrawlStatus.crawling.value,
            started_at=datetime.now(UTC),
        )
    )
    await session.commit()
    await session.refresh(job)
    return job


async def _run_job(
    job: DbCrawlJob,
    sync_redis: redis_lib.Redis,
    async_redis: aioredis.Redis,
) -> None:
    payload_data = job.config or {}
    if not payload_data:
        async with async_session_maker() as session:
            store = JobStore(session=session, redis_client=sync_redis)
            await store.update(
                job.job_id,
                status=CrawlStatus.failed,
                error={
                    "code": "invalid_job_payload",
                    "message": "Scrape job payload missing.",
                },
            )
        return

    from app.models.requests import ScrapeRequest

    scrape_payload = ScrapeRequest(**payload_data)

    async with async_session_maker() as session:
        store = JobStore(session=session, redis_client=sync_redis)
        try:
            await execute_sync_scrape(
                payload=scrape_payload,
                tenant_id=job.tenant_id,
                request_id=job.job_id,
                store=store,
                redis_client=async_redis,
                job_id=job.job_id,
            )
        except Exception as exc:
            logger.exception("job=%s unhandled scrape worker error: %s", job.job_id, exc)
            await store.update(
                job.job_id,
                status=CrawlStatus.failed,
                error={"code": "internal_error", "message": str(exc)},
            )


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Scrape worker starting")

    sync_redis = redis_lib.Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=5
    )
    async_redis = aioredis.Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=5
    )

    active: set[asyncio.Task] = set()
    semaphore = asyncio.Semaphore(settings.active_workers)

    async def _run_with_semaphore(job: DbCrawlJob) -> None:
        async with semaphore:
            await _run_job(job, sync_redis, async_redis)

    try:
        while True:
            done = {task for task in active if task.done()}
            active -= done

            slots = settings.active_workers - len(active)
            for _ in range(slots):
                async with async_session_maker() as session:
                    job = await _claim_queued_scrape_job(session)
                if job is None:
                    break

                logger.info("Dispatching scrape job=%s", job.job_id)
                task = asyncio.create_task(_run_with_semaphore(job))
                active.add(task)

            await asyncio.sleep(_POLL_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Scrape worker shutting down")
        if active:
            await asyncio.gather(*active, return_exceptions=True)
    finally:
        sync_redis.close()
        await async_redis.aclose()
        logger.info("Scrape worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
