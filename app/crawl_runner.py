# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
Crawl runner ” background worker process.

Responsibilities
----------------
1. Poll PostgreSQL for jobs in `queued` status.
2. Claim each job ( `fetching_sitemap` / `crawling`).
3. Seed RabbitMQ queue via `Frontier.start()`.
4. Consume messages from RabbitMQ, call fetch  extract  classify,
   persist each `ScrapedDocument`, update job progress in Redis.
5. On exhaustion  transition to `done` (or `partial` / `failed`).
6. Fire the configured `callback_url` webhook if present.

Concurrency
-----------
`ACTIVE_WORKERS` (env var, default 4) controls how many jobs run
simultaneously; each job gets its own asyncio task.

Cancellation
------------
Between message pulls the runner checks whether the job's DB status
has been externally set to `cancelled` and stops gracefully.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

import aio_pika
import redis as redis_lib
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import JOB_ID_PREFIX_CRAWL, REDIS_PREFIX_JOB_KNOWN_HASHES
from app.db import async_session_maker
from app.models.crawl import CrawlConfig, CrawlProgress
from app.models.db import DbCrawlJob, DbScrapedDocument
from app.models.enums import CrawlStatus
from app.services.browser import render_page
from app.services.classifier import classify_document
from app.services.extractor import extract
from app.services.fetcher import FetchError, fetch
from app.services.frontier import Frontier, FrontierConfig
from app.services.mime_utils import content_type_from_mime
from app.services.pii_redactor import redact_pii as redact_pii_text
from app.services.webhooks import WebhookPayload, publish_webhook
from app.settings import settings

logger = logging.getLogger(__name__)

# How long to sleep between polls when no queued jobs are found (seconds)
_POLL_INTERVAL = 5
# How many messages to prefetch per worker from RabbitMQ
_PREFETCH = 4
# How long (seconds) to wait for more messages before declaring the queue empty
_QUEUE_DRAIN_TIMEOUT = 10


# ---------------------------------------------------------------------------
# DB helpers (sync-style wrappers that take an existing AsyncSession)
# ---------------------------------------------------------------------------


async def _claim_queued_job(session: AsyncSession) -> DbCrawlJob | None:
    """
    Atomically fetch one queued job and transition it to `fetching_sitemap`.

    Uses SELECT ¦ FOR UPDATE SKIP LOCKED so concurrent runner instances
    don't race on the same row.
    """
    stmt = (
        select(DbCrawlJob)
        .where(DbCrawlJob.status == CrawlStatus.queued.value)
        .where(DbCrawlJob.job_id.like(f"{JOB_ID_PREFIX_CRAWL}%"))
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
            status=CrawlStatus.fetching_sitemap.value,
            started_at=datetime.now(UTC),
        )
    )
    await session.commit()
    await session.refresh(job)
    return job


async def _set_job_status(
    session: AsyncSession,
    job_id: str,
    status: CrawlStatus,
    *,
    error: dict | None = None,
) -> None:
    values: dict = {"status": status.value}
    if status in (CrawlStatus.done, CrawlStatus.failed, CrawlStatus.cancelled, CrawlStatus.partial):
        values["completed_at"] = datetime.now(UTC)
    if error:
        values["error"] = error
    await session.execute(update(DbCrawlJob).where(DbCrawlJob.job_id == job_id).values(**values))
    await session.commit()


async def _is_cancelled(session: AsyncSession, job_id: str) -> bool:
    result = await session.execute(select(DbCrawlJob.status).where(DbCrawlJob.job_id == job_id))
    row = result.scalar_one_or_none()
    return row == CrawlStatus.cancelled.value


async def _persist_document(
    session: AsyncSession,
    job_id: str,
    tenant_id: str,
    doc: dict,
    redact_pii: bool = False,
    async_redis: object | None = None,
) -> None:
    """Write one scraped document row; silently skip duplicates.

    Honors incremental baseline stored in Redis under
    REDIS_PREFIX_JOB_KNOWN_HASHES:{job_id} — if the document's
    content_hash is present there, the document is skipped.
    """
    extraction = doc.get("extraction")
    if extraction is None:
        return

    raw_text: str = extraction.raw_text or ""
    if redact_pii:
        raw_text = redact_pii_text(raw_text)

    mime_type: str = doc.get("mime_type", "text/html")

    # Delta-check: skip if content_hash already in known set for this job
    content_hash = extraction.content_hash
    if async_redis and content_hash:
        try:
            key = f"{REDIS_PREFIX_JOB_KNOWN_HASHES}:{job_id}"
            is_known = await async_redis.sismember(key, content_hash)
            if is_known:
                logger.info("job=%s skipping known content_hash=%s", job_id, content_hash)
                return
        except Exception:
            # On redis errors, fall back to normal persist
            pass

    doc_type, doc_type_confidence, _ = classify_document(doc.get("final_url"), raw_text)

    db_doc = DbScrapedDocument(
        document_id=f"d_{uuid4().hex[:12]}",
        job_id=job_id,
        tenant_id=tenant_id,
        source_url=doc.get("source_url", ""),
        canonical_url=extraction.canonical_url,
        mime_type=mime_type,
        content_type=content_type_from_mime(mime_type).value,
        raw_text=raw_text,
        raw_html=doc.get("raw_html"),
        binary_url=None,
        doc_type=doc_type.value,
        doc_type_confidence=doc_type_confidence,
        title=extraction.title,
        language=extraction.language,
        published_at=extraction.published_at,
        page_count=extraction.page_count,
        content_length=extraction.content_length,
        content_hash=content_hash,
        metadata_={
            "discovered_at": datetime.now(UTC).isoformat(),
            "http_status": doc.get("http_status"),
            "response_time_ms": doc.get("response_time_ms"),
            "redirect_chain": doc.get("redirect_chain", []),
            "used_playwright": doc.get("used_playwright", False),
            "warnings": doc.get("warnings", []),
            "pii_redacted": redact_pii,
        },
        extraction_confidence=doc_type_confidence,
        warnings=doc.get("warnings", []) + extraction.warnings,
    )
    session.add(db_doc)
    try:
        await session.commit()
        # After successful commit, add the content_hash to known set for future deltas
        try:
            if async_redis and content_hash:
                key = f"{REDIS_PREFIX_JOB_KNOWN_HASHES}:{job_id}"
                await async_redis.sadd(key, content_hash)
        except Exception:
            pass
    except Exception:
        await session.rollback()
        logger.warning("Duplicate document skipped for job %s", job_id)


async def _update_progress_from_redis(
    session: AsyncSession,
    job_id: str,
    redis: redis_lib.Redis,
    status: CrawlStatus,
) -> None:
    """Read frontier progress counters from Redis and write them to Postgres."""
    raw = redis.hgetall(f"JOB:progress:{job_id}")
    progress = CrawlProgress(
        stage=status.value,
        urls_discovered=int(raw.get("urls_discovered", 0)),
        urls_fetched=int(raw.get("urls_fetched", 0)),
        documents_extracted=int(raw.get("urls_fetched", 0)),  # 1:1 for now
        documents_classified=int(raw.get("urls_fetched", 0)),
        urls_pending=int(raw.get("urls_pending", 0)),
        bytes_downloaded=int(raw.get("bytes_downloaded", 0)),
    )
    await session.execute(
        update(DbCrawlJob)
        .where(DbCrawlJob.job_id == job_id)
        .values(progress=progress.model_dump(), status=status.value)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Per-job fetch adapter (bridges fetcher.py interface to Frontier's fetch_fn)
# ---------------------------------------------------------------------------


async def _fetch_for_frontier(
    url: str,
    cfg: FrontierConfig,
    *,
    redis_client: object | None = None,
) -> object:
    """Thin adapter: call app.services.fetcher.fetch with frontier config."""
    return await fetch(
        url,
        user_agent=cfg.user_agent,
        follow_redirects=True,
        timeout_ms=cfg.timeout_ms,
        max_pdf_size_mb=cfg.max_pdf_size_mb,
        respect_robots_txt=cfg.respect_robots_txt,
        max_requests_per_second=cfg.max_requests_per_second,
        redis=redis_client,
    )


# ---------------------------------------------------------------------------
# Core per-job coroutine
# ---------------------------------------------------------------------------


async def run_job(
    job: DbCrawlJob,
    rmq_connection: aio_pika.abc.AbstractRobustConnection,
    redis: redis_lib.Redis,
) -> None:
    """Drive one crawl job from queued  done/failed/partial."""
    job_id: str = job.job_id
    tenant_id: str = job.tenant_id
    config_data: dict = job.config or {}

    logger.info("job=%s starting crawl for tenant=%s", job_id, tenant_id)

    config = CrawlConfig(**config_data)

    frontier_cfg = FrontierConfig(
        job_id=job_id,
        tenant_id=tenant_id,
        allowed_domains=config.allowed_domains,
        max_depth=config.max_depth,
        max_pages=config.max_pages,
        include_patterns=config.include_patterns,
        exclude_patterns=config.exclude_patterns,
        follow_pdfs=config.follow_pdfs,
        render_javascript=config.render_javascript.value
        if hasattr(config.render_javascript, "value")
        else str(config.render_javascript),
        sitemap_hint_url=str(config.sitemap_hint_url) if config.sitemap_hint_url else None,
        user_agent=config.user_agent or "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)",
        max_requests_per_second=config.max_requests_per_second,
        respect_robots_txt=config.respect_robots_txt,
        max_pdf_size_mb=config.max_pdf_size_mb,
    )

    # Use async Redis for the frontier (it needs async SADD/INCR/HSET)
    import redis.asyncio as aioredis

    async_redis = aioredis.Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=5
    )

    frontier = Frontier(frontier_cfg, redis=async_redis, rmq_connection=rmq_connection)

    docs_saved = 0
    terminal_status = CrawlStatus.done

    try:
        # â”€â”€ Phase 1: seed the queue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        async with async_session_maker() as session:
            await session.execute(
                update(DbCrawlJob)
                .where(DbCrawlJob.job_id == job_id)
                .values(status=CrawlStatus.fetching_sitemap.value)
            )
            await session.commit()

        await frontier.start([str(u) for u in config.seed_urls])

        # â”€â”€ Phase 2: consume messages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        channel = await rmq_connection.channel()
        await channel.set_qos(prefetch_count=_PREFETCH)

        # The queue was already declared by frontier.start() via _ensure_channel
        queue = await channel.get_queue(f"urls.{job_id}")

        async with async_session_maker() as session:
            await session.execute(
                update(DbCrawlJob)
                .where(DbCrawlJob.job_id == job_id)
                .values(status=CrawlStatus.crawling.value)
            )
            await session.commit()

        logger.info("job=%s entering message loop", job_id)

        empty_streak = 0

        async with async_session_maker() as session:
            while True:
                # Cancellation check
                if await _is_cancelled(session, job_id):
                    logger.info("job=%s externally cancelled", job_id)
                    terminal_status = CrawlStatus.cancelled
                    break

                # Try to get one message with a short timeout
                try:
                    message = await asyncio.wait_for(
                        queue.get(timeout=_QUEUE_DRAIN_TIMEOUT),
                        timeout=_QUEUE_DRAIN_TIMEOUT + 1,
                    )
                except (TimeoutError, aio_pika.exceptions.QueueEmpty):
                    empty_streak += 1
                    if empty_streak >= 2:
                        # Queue has been empty for two consecutive polls  done
                        logger.info("job=%s queue drained (docs=%d)", job_id, docs_saved)
                        break
                    await asyncio.sleep(1)
                    continue
                except Exception as exc:
                    logger.warning("job=%s queue.get error: %s", job_id, exc)
                    empty_streak += 1
                    if empty_streak >= 3:
                        terminal_status = CrawlStatus.partial
                        break
                    await asyncio.sleep(2)
                    continue

                empty_streak = 0  # reset on successful receive

                async with message.process(ignore_processed=True):
                    try:
                        doc = await frontier.process_message(
                            message.body,
                            fetch_fn=lambda url, cfg: _fetch_for_frontier(
                                url,
                                cfg,
                                redis_client=async_redis,
                            ),
                            extract_fn=extract,
                            browser_render_fn=render_page,
                        )
                        await _persist_document(
                            session,
                            job_id,
                            tenant_id,
                            doc,
                            redact_pii=config.redact_pii,
                            async_redis=async_redis,
                        )
                        docs_saved += 1

                        # Periodically flush progress to DB
                        if docs_saved % 10 == 0:
                            await _update_progress_from_redis(
                                session, job_id, redis, CrawlStatus.crawling
                            )
                    except FetchError as exc:
                        logger.warning("job=%s fetch error for message: %s", job_id, exc)
                        # Don't abort whole job on individual URL failures

        # â”€â”€ Phase 3: finalize â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        await channel.close()

        async with async_session_maker() as session:
            await _update_progress_from_redis(session, job_id, redis, terminal_status)

        logger.info(
            "job=%s finished status=%s docs=%d",
            job_id,
            terminal_status.value,
            docs_saved,
        )

    except Exception as exc:
        logger.exception("job=%s unhandled error: %s", job_id, exc)
        terminal_status = CrawlStatus.failed
        async with async_session_maker() as session:
            await _set_job_status(
                session,
                job_id,
                CrawlStatus.failed,
                error={"code": "internal_error", "message": str(exc)},
            )
    finally:
        await async_redis.aclose()
        try:
            await frontier.close()
        except Exception:
            pass

    # â”€â”€ Webhook dispatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    callback_url: str | None = job.callback_url
    if callback_url and terminal_status != CrawlStatus.cancelled:
        event_map = {
            CrawlStatus.done: "crawl.completed",
            CrawlStatus.failed: "crawl.failed",
            CrawlStatus.partial: "crawl.completed",
        }
        event = event_map.get(terminal_status, "crawl.completed")
        payload = WebhookPayload(
            event=event,
            job_id=job_id,
            tenant_id=tenant_id,
            status=terminal_status.value,
            stats={"documents_extracted": docs_saved},
            completed_at=datetime.now(UTC).isoformat(),
            at=datetime.now(UTC).isoformat(),
            documents_url=f"/v1/jobs/{job_id}/documents",
            callback_url=callback_url,
        )
        await publish_webhook(settings.rabbitmq_url, payload)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def main() -> None:
    """Poll for queued jobs and dispatch them as concurrent tasks."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Crawl runner starting (active_workers=%d)", settings.active_workers)

    # Sync Redis for DB-progress writes (JobStore uses sync redis.Redis)
    redis_client = redis_lib.Redis.from_url(
        settings.redis_url, decode_responses=True, socket_connect_timeout=5
    )

    rmq_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    logger.info("Connected to RabbitMQ: %s", settings.rabbitmq_url)

    semaphore = asyncio.Semaphore(settings.active_workers)
    active: set[asyncio.Task] = set()

    async def _run_with_semaphore(job: DbCrawlJob) -> None:
        async with semaphore:
            try:
                await run_job(job, rmq_connection, redis_client)
            except Exception:
                logger.exception("Unhandled error in run_job for %s", job.job_id)

    try:
        while True:
            # Reap finished tasks
            done = {t for t in active if t.done()}
            active -= done

            slots = settings.active_workers - len(active)

            for _ in range(slots):
                async with async_session_maker() as session:
                    job = await _claim_queued_job(session)

                if job is None:
                    break  # No more queued jobs right now

                logger.info("Dispatching job=%s", job.job_id)
                task = asyncio.create_task(_run_with_semaphore(job))
                active.add(task)

            await asyncio.sleep(_POLL_INTERVAL)

    except asyncio.CancelledError:
        logger.info("Crawl runner shutting down ” waiting for active jobs¦")
        if active:
            await asyncio.gather(*active, return_exceptions=True)
    finally:
        await rmq_connection.close()
        redis_client.close()
        logger.info("Crawl runner stopped.")


if __name__ == "__main__":
    asyncio.run(main())
