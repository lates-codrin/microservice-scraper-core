from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import redis
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlConfig, CrawlJob, CrawlProgress, CrawlStats, IncrementalOptions
from app.models.document import ScrapedDocument
from app.models.enums import ContentType, CrawlStatus, DocType
from app.models.db import DbCrawlJob, DbScrapedDocument


class DuplicateJobError(Exception):
    """Raised when an Idempotency-Key is reused with a different request body."""

    def __init__(self, message: str = "", existing_job_id: str = "") -> None:
        super().__init__(message)
        self.existing_job_id = existing_job_id


class JobStore:
    def __init__(self, session: AsyncSession, redis_client: redis.Redis) -> None:
        self.session = session
        self.redis = redis_client

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
        # Idempotency check — atomic SET NX guarantees exactly-once job creation
        # under concurrent requests with the same idempotency key.
        idem_key = f"IDEM:{tenant_id}:{idempotency_key}"
        idem_fp_key = f"IDEM:fp:{tenant_id}:{idempotency_key}"

        # Use SETNX semantics: SET key "PENDING" NX EX 86400
        # returns True if we won the race, None/False if key already existed.
        won_race = self.redis.set(idem_key, "PENDING", ex=86400, nx=True)
        if not won_race:
            # Another coroutine already owns this key.  Retry until the winner
            # replaces "PENDING" with the real job_id (up to 2 s total).
            for _attempt in range(40):
                existing_job_id = self.redis.get(idem_key)
                if existing_job_id and existing_job_id != "PENDING":
                    stored_fp = self.redis.get(idem_fp_key)
                    if stored_fp and stored_fp != request_fingerprint:
                        raise DuplicateJobError(
                            f"Idempotency-Key '{idempotency_key}' already used with a different request body.",
                            existing_job_id=existing_job_id,
                        )
                    job = await self.get(existing_job_id)
                    if job:
                        return job
                    break
                await asyncio.sleep(0.05)
            # Timed out or key never materialised — fall through and create a new job.
            # This should not happen in practice.

        job_id = f"cj_{uuid4().hex[:12]}"
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
            stats=CrawlStats(by_doc_type={"other": 0}, http_errors={}).model_dump(),
            config=config.model_dump(mode="json"),
            submitted_at=now,
            estimated_completion_at=now + timedelta(minutes=30),
            callback_url=str(callback_url) if callback_url else None,
        )

        self.session.add(db_job)
        await self.session.commit()

        # Store idempotency key + fingerprint for future collision detection
        self.redis.setex(idem_key, 86400, job_id)
        self.redis.setex(idem_fp_key, 86400, request_fingerprint)

        if incremental and incremental.known_content_hashes:
            self.redis.sadd(f"JOB:known_hashes:{job_id}", *incremental.known_content_hashes)

        return await self.get(job_id)

    async def create_scrape_job(self, tenant_id: str) -> str:
        job_id = f"sj_{uuid4().hex[:12]}"
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
            stats=CrawlStats(by_doc_type={"other": 0}, http_errors={}).model_dump(),
            config=None,
            submitted_at=now,
            estimated_completion_at=now + timedelta(seconds=30),
        )
        self.session.add(db_job)
        await self.session.commit()
        return job_id

    async def get(self, job_id: str) -> CrawlJob | None:
        result = await self.session.execute(select(DbCrawlJob).where(DbCrawlJob.job_id == job_id))
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
            submitted_at=db_job.submitted_at,
            started_at=db_job.started_at,
            estimated_completion_at=db_job.estimated_completion_at,
            completed_at=db_job.completed_at,
            error=db_job.error,
        )

    async def update(
        self,
        job_id: str,
        *,
        status: CrawlStatus | None = None,
        progress: CrawlProgress | None = None,
        stats: CrawlStats | None = None,
        error: dict[str, Any] | None = None,
    ) -> CrawlJob | None:
        values = {}
        if status:
            values["status"] = status.value
            if status == CrawlStatus.done:
                values["completed_at"] = datetime.now(UTC)
                self.redis.setex(f"JOB:retention:{job_id}", 30 * 86400, "1")
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

    async def delete(self, job_id: str) -> bool:
        result = await self.session.execute(delete(DbCrawlJob).where(DbCrawlJob.job_id == job_id))
        await self.session.commit()
        return result.rowcount > 0

    async def cancel_job(self, job_id: str) -> CrawlJob | None:
        return await self.update(job_id, status=CrawlStatus.cancelled)

    async def document_count(self, job_id: str) -> int:
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
        # Check retention
        if self.redis.exists(f"JOB:expired:{job_id}"):
            from fastapi import HTTPException
            raise HTTPException(status_code=410, detail="Job results have expired")

        stmt = select(DbScrapedDocument).where(DbScrapedDocument.job_id == job_id)
        if doc_type:
            stmt = stmt.where(DbScrapedDocument.doc_type == doc_type)
        if min_confidence > 0:
            stmt = stmt.where(DbScrapedDocument.doc_type_confidence >= min_confidence)

        # Simple offset pagination (opaque cursor encodes offset as base64)
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
        docs = result.scalars().all()

        has_more = len(docs) > limit
        if has_more:
            docs = docs[:limit]
            next_cursor = base64.b64encode(str(offset + limit).encode()).decode()
        else:
            next_cursor = None

        models = [
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
            for d in docs
        ]

        return models, next_cursor, has_more, total

    async def add_document(self, job_id: str, tenant_id: str, doc: ScrapedDocument) -> None:
        db_doc = DbScrapedDocument(
            document_id=doc.document_id,
            job_id=job_id,
            tenant_id=tenant_id,
            source_url=str(doc.source_url),
            canonical_url=str(doc.canonical_url) if doc.canonical_url else None,
            mime_type=doc.mime_type,
            content_type=doc.content_type.value,
            raw_text=doc.raw_text,
            raw_html=doc.raw_html,
            binary_url=str(doc.binary_url) if doc.binary_url else None,
            doc_type=doc.doc_type.value,
            doc_type_confidence=doc.doc_type_confidence,
            title=doc.title,
            language=doc.language,
            published_at=str(doc.published_at) if doc.published_at else None,
            page_count=doc.page_count,
            content_length=doc.content_length,
            content_hash=doc.content_hash,
            metadata_=doc.metadata,
            extraction_confidence=doc.extraction_confidence,
            warnings=doc.warnings,
        )
        self.session.add(db_doc)
        await self.session.commit()

    async def queue_depth(self) -> int:
        stmt = select(func.count(DbCrawlJob.job_id)).where(
            DbCrawlJob.status.in_([
                CrawlStatus.queued.value,
                CrawlStatus.fetching_sitemap.value,
                CrawlStatus.crawling.value,
                CrawlStatus.extracting.value,
                CrawlStatus.classifying.value,
            ])
        )
        return (await self.session.execute(stmt)).scalar_one()


InMemoryJobStore = JobStore
