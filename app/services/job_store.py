# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Persistent job store backed by PostgreSQL + Redis."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ESTIMATED_CRAWL_COMPLETION_MINUTES,
    ESTIMATED_SCRAPE_COMPLETION_SECONDS,
    IDEMPOTENCY_KEY_TTL_SECONDS,
    IDEMPOTENCY_PENDING_SENTINEL,
    IDEMPOTENCY_RACE_POLL_ATTEMPTS,
    IDEMPOTENCY_RACE_POLL_INTERVAL,
    JOB_ID_PREFIX_CRAWL,
    JOB_ID_PREFIX_SCRAPE,
    JOB_RETENTION_TTL_SECONDS,
    REDIS_PREFIX_IDEMPOTENCY,
    REDIS_PREFIX_IDEMPOTENCY_FINGERPRINT,
    REDIS_PREFIX_JOB_EXPIRED,
    REDIS_PREFIX_JOB_KNOWN_HASHES,
    REDIS_PREFIX_JOB_RETENTION,
)
from app.models.crawl import (
    CrawlConfig,
    CrawlJob,
    CrawlProgress,
    CrawlStats,
    IncrementalOptions,
)
from app.models.db import DbCrawlJob, DbScrapedDocument
from app.models.document import ScrapedDocument
from app.models.enums import ContentType, CrawlStatus, DocType
from app.services.state_machine import InvalidTransitionError, validate_transition

logger = logging.getLogger(__name__)


class DuplicateJobError(Exception):
    """Raised when an Idempotency-Key is reused with a different request body."""

    def __init__(self, message: str = "", existing_job_id: str = "") -> None:
        super().__init__(message)
        self.existing_job_id = existing_job_id


class JobStore:
    """Persistent store for crawl/scrape jobs and their documents."""

    def __init__(self, session: AsyncSession, redis_client: redis.Redis) -> None:
        self.session = session
        self.redis = redis_client

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_crawl_job(
        self,
        tenant_id: str,
        config: CrawlConfig,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        incremental: IncrementalOptions | None = None,
        callback_url: Any | None = None,
    ) -> CrawlJob:
        """Create a new crawl job with idempotency protection."""
        idem_key = f"{REDIS_PREFIX_IDEMPOTENCY}:{tenant_id}:{idempotency_key}"
        idem_fp_key = (
            f"{REDIS_PREFIX_IDEMPOTENCY_FINGERPRINT}:{tenant_id}:{idempotency_key}"
        )

        # Atomic SET NX guarantees exactly-once job creation
        won_race = self.redis.set(
            idem_key,
            IDEMPOTENCY_PENDING_SENTINEL,
            ex=IDEMPOTENCY_KEY_TTL_SECONDS,
            nx=True,
        )
        if not won_race:
            for _attempt in range(IDEMPOTENCY_RACE_POLL_ATTEMPTS):
                existing_job_id = self.redis.get(idem_key)
                if (
                    existing_job_id
                    and existing_job_id != IDEMPOTENCY_PENDING_SENTINEL
                ):
                    stored_fp = self.redis.get(idem_fp_key)
                    if stored_fp and stored_fp != request_fingerprint:
                        raise DuplicateJobError(
                            f"Idempotency-Key '{idempotency_key}' already used "
                            "with a different request body.",
                            existing_job_id=existing_job_id,
                        )
                    job = await self.get(existing_job_id)
                    if job:
                        return job
                    break
                await asyncio.sleep(IDEMPOTENCY_RACE_POLL_INTERVAL)

        job_id = f"{JOB_ID_PREFIX_CRAWL}{uuid4().hex[:12]}"
        now = datetime.now(UTC)

        db_job = DbCrawlJob(
            job_id=job_id,
            tenant_id=tenant_id,
            status=CrawlStatus.queued.value,
            progress=CrawlProgress(
                stage=CrawlStatus.queued.value,
                urls_discovered=0,
                urls_fetched=0,
                documents_extracted=0,
                documents_classified=0,
                urls_pending=0,
                bytes_downloaded=0,
            ).model_dump(),
            stats=CrawlStats(
                by_doc_type={"other": 0}, http_errors={}
            ).model_dump(),
            config=config.model_dump(mode="json"),
            submitted_at=now,
            estimated_completion_at=now
            + timedelta(minutes=ESTIMATED_CRAWL_COMPLETION_MINUTES),
            callback_url=str(callback_url) if callback_url else None,
        )

        self.session.add(db_job)
        await self.session.commit()

        # Materialise idempotency key + fingerprint for future collision detection
        self.redis.setex(idem_key, IDEMPOTENCY_KEY_TTL_SECONDS, job_id)
        self.redis.setex(idem_fp_key, IDEMPOTENCY_KEY_TTL_SECONDS, request_fingerprint)

        if incremental and incremental.known_content_hashes:
            self.redis.sadd(
                f"{REDIS_PREFIX_JOB_KNOWN_HASHES}:{job_id}",
                *incremental.known_content_hashes,
            )

        result = await self.get(job_id)
        assert result is not None  # noqa: S101 ” just-created job must exist
        return result

    async def create_scrape_job(self, tenant_id: str) -> str:
        """Create a lightweight single-URL scrape job."""
        job_id = f"{JOB_ID_PREFIX_SCRAPE}{uuid4().hex[:12]}"
        now = datetime.now(UTC)
        db_job = DbCrawlJob(
            job_id=job_id,
            tenant_id=tenant_id,
            status=CrawlStatus.queued.value,
            progress=CrawlProgress(
                stage=CrawlStatus.queued.value,
                urls_discovered=0,
                urls_fetched=0,
                documents_extracted=0,
                documents_classified=0,
                urls_pending=0,
                bytes_downloaded=0,
            ).model_dump(),
            stats=CrawlStats(
                by_doc_type={"other": 0}, http_errors={}
            ).model_dump(),
            config=None,
            submitted_at=now,
            estimated_completion_at=now
            + timedelta(seconds=ESTIMATED_SCRAPE_COMPLETION_SECONDS),
        )
        self.session.add(db_job)
        await self.session.commit()
        return job_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(
        self,
        job_id: str,
        tenant_id: str | None = None,
    ) -> CrawlJob | None:
        """Fetch a job by ID, optionally filtering by tenant."""
        stmt = select(DbCrawlJob).where(DbCrawlJob.job_id == job_id)
        if tenant_id is not None:
            stmt = stmt.where(DbCrawlJob.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        db_job = result.scalar_one_or_none()
        if not db_job:
            return None

        return CrawlJob(
            job_id=db_job.job_id,
            tenant_id=db_job.tenant_id,
            status=CrawlStatus(db_job.status),
            progress=CrawlProgress(**db_job.progress) if db_job.progress else None,
            stats=CrawlStats(**db_job.stats) if db_job.stats else None,
            config=CrawlConfig(**db_job.config) if db_job.config else None,
            callback_url=db_job.callback_url,
            submitted_at=db_job.submitted_at,
            started_at=db_job.started_at,
            estimated_completion_at=db_job.estimated_completion_at,
            completed_at=db_job.completed_at,
            error=db_job.error,
        )

    # ------------------------------------------------------------------
    # Update (with state machine enforcement)
    # ------------------------------------------------------------------

    async def update(
        self,
        job_id: str,
        *,
        status: CrawlStatus | None = None,
        progress: CrawlProgress | None = None,
        stats: CrawlStats | None = None,
        error: dict[str, Any] | None = None,
    ) -> CrawlJob | None:
        """Update a job, enforcing valid status transitions."""
        if status is not None:
            # Fetch current status for state machine validation
            current_job = await self.get(job_id)
            if current_job is None:
                return None
            try:
                validate_transition(job_id, current_job.status, status)
            except InvalidTransitionError:
                logger.warning(
                    "Rejected transition %s  %s for job %s",
                    current_job.status.value,
                    status.value,
                    job_id,
                )
                raise

        values: dict[str, Any] = {}
        if status:
            values["status"] = status.value
            if status == CrawlStatus.done:
                values["completed_at"] = datetime.now(UTC)
                self.redis.setex(
                    f"{REDIS_PREFIX_JOB_RETENTION}:{job_id}",
                    JOB_RETENTION_TTL_SECONDS,
                    "1",
                )
            elif status == CrawlStatus.failed:
                values["completed_at"] = datetime.now(UTC)
            elif status == CrawlStatus.cancelled:
                values["completed_at"] = datetime.now(UTC)
        if progress:
            values["progress"] = progress.model_dump()
        if stats:
            values["stats"] = stats.model_dump()
        if error:
            values["error"] = error

        if not values:
            return await self.get(job_id)

        await self.session.execute(
            update(DbCrawlJob).where(DbCrawlJob.job_id == job_id).values(**values)
        )
        await self.session.commit()
        return await self.get(job_id)

    # ------------------------------------------------------------------
    # Delete / Cancel
    # ------------------------------------------------------------------

    async def delete(self, job_id: str) -> bool:
        """Hard-delete a job and its documents."""
        result = await self.session.execute(
            delete(DbCrawlJob).where(DbCrawlJob.job_id == job_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def cancel_job(self, job_id: str) -> CrawlJob | None:
        """Move job to cancelled state."""
        current_job = await self.get(job_id)
        if current_job is None:
            return None

        await self.session.execute(
            update(DbCrawlJob)
            .where(DbCrawlJob.job_id == job_id)
            .values(
                status=CrawlStatus.cancelled.value,
                completed_at=datetime.now(UTC),
            )
        )
        await self.session.commit()
        return await self.get(job_id)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def document_count(self, job_id: str) -> int:
        """Count documents belonging to a job."""
        stmt = select(func.count(DbScrapedDocument.document_id)).where(
            DbScrapedDocument.job_id == job_id
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def get_documents(
        self,
        job_id: str,
        *,
        cursor: str | None,
        limit: int,
        doc_type: str | None,
        min_confidence: float,
        changed_only: bool = False,
    ) -> tuple[list[ScrapedDocument], str | None, bool, int]:
        """Paginated document retrieval with optional filters."""
        # Check retention expiry
        if self.redis.exists(f"{REDIS_PREFIX_JOB_EXPIRED}:{job_id}"):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=410, detail="Job results have expired"
            )

        stmt = select(DbScrapedDocument).where(
            DbScrapedDocument.job_id == job_id
        )
        if doc_type:
            stmt = stmt.where(DbScrapedDocument.doc_type == doc_type)
        if min_confidence > 0:
            stmt = stmt.where(
                DbScrapedDocument.doc_type_confidence >= min_confidence
            )

        # Opaque cursor: base64-encoded offset integer
        offset = 0
        if cursor:
            try:
                offset = int(base64.b64decode(cursor).decode())
            except Exception:
                pass

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(offset).limit(limit + 1)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
            next_cursor = base64.b64encode(
                str(offset + limit).encode()
            ).decode()
        else:
            next_cursor = None

        documents = [
            ScrapedDocument(
                document_id=d.document_id,
                source_url=d.source_url,
                canonical_url=d.canonical_url,
                mime_type=d.mime_type,
                content_type=ContentType(d.content_type),
                raw_text=d.raw_text,
                raw_html=d.raw_html,
                binary_url=d.binary_url,
                doc_type=DocType(d.doc_type),
                doc_type_confidence=d.doc_type_confidence,
                title=d.title,
                language=d.language,
                published_at=d.published_at,
                page_count=d.page_count,
                content_length=d.content_length,
                content_hash=d.content_hash,
                metadata=d.metadata_,
                extraction_confidence=d.extraction_confidence,
                warnings=d.warnings,
            )
            for d in rows
        ]

        return documents, next_cursor, has_more, total

    async def add_document(
        self,
        job_id: str,
        tenant_id: str,
        document: ScrapedDocument,
    ) -> None:
        """Persist a scraped document linked to a job."""
        db_doc = DbScrapedDocument(
            document_id=document.document_id,
            job_id=job_id,
            tenant_id=tenant_id,
            source_url=str(document.source_url),
            canonical_url=(
                str(document.canonical_url) if document.canonical_url else None
            ),
            mime_type=document.mime_type,
            content_type=document.content_type.value,
            raw_text=document.raw_text,
            raw_html=document.raw_html,
            binary_url=(
                str(document.binary_url) if document.binary_url else None
            ),
            doc_type=document.doc_type.value,
            doc_type_confidence=document.doc_type_confidence,
            title=document.title,
            language=document.language,
            published_at=(
                str(document.published_at) if document.published_at else None
            ),
            page_count=document.page_count,
            content_length=document.content_length,
            content_hash=document.content_hash,
            metadata_=document.metadata,
            extraction_confidence=document.extraction_confidence,
            warnings=document.warnings,
        )
        self.session.add(db_doc)
        await self.session.commit()

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def queue_depth(self) -> int:
        """Count jobs in non-terminal states."""
        stmt = select(func.count(DbCrawlJob.job_id)).where(
            DbCrawlJob.status.in_(
                [
                    CrawlStatus.queued.value,
                    CrawlStatus.fetching_sitemap.value,
                    CrawlStatus.crawling.value,
                    CrawlStatus.extracting.value,
                    CrawlStatus.classifying.value,
                ]
            )
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def delete_jobs_before(self, cutoff_dt: datetime) -> int:
        """Delete jobs and documents created before cutoff datetime (GDPR compliance).
        
        Args:
            cutoff_dt: Delete jobs with submitted_at before this time
            
        Returns:
            Number of job records deleted
        """
        # Delete associated documents first (foreign key constraint)
        stmt = delete(DbScrapedDocument).where(
            DbScrapedDocument.job_id.in_(
                select(DbCrawlJob.job_id).where(DbCrawlJob.submitted_at < cutoff_dt)
            )
        )
        await self.session.execute(stmt)
        
        # Delete jobs
        stmt = delete(DbCrawlJob).where(DbCrawlJob.submitted_at < cutoff_dt)
        result = await self.session.execute(stmt)
        deleted = result.rowcount
        
        await self.session.commit()
        logger.info("Log retention: deleted %d jobs before %s", deleted, cutoff_dt)
        return deleted


__all__ = ["DuplicateJobError", "JobStore"]

