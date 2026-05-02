# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Job management endpoints ” GET, DELETE, cancel, documents."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.constants import (
    RETRY_AFTER_CLASSIFYING,
    RETRY_AFTER_CRAWLING,
    RETRY_AFTER_EXTRACTING,
    RETRY_AFTER_FETCHING_SITEMAP,
    RETRY_AFTER_QUEUED,
)
from app.dependencies import get_job_store
from app.models.common import ErrorEnvelope, ErrorPayload
from app.models.crawl import CrawlJob
from app.models.enums import CrawlStatus, DocType
from app.models.responses import CancelJobResponse, DocumentPageResponse
from app.services.job_store import JobStore

router = APIRouter(prefix="/v1/jobs", tags=["job"])

_FRESH_JOB_GRACE_SECONDS = 60


def _is_valid_job_id(job_id: str) -> bool:
    return job_id.startswith(("cj_", "sj_"))


# Mapping of non-terminal states to Retry-After header values.
_RETRY_AFTER_BY_STATUS: dict[CrawlStatus, int] = {
    CrawlStatus.queued: RETRY_AFTER_QUEUED,
    CrawlStatus.fetching_sitemap: RETRY_AFTER_FETCHING_SITEMAP,
    CrawlStatus.crawling: RETRY_AFTER_CRAWLING,
    CrawlStatus.extracting: RETRY_AFTER_EXTRACTING,
    CrawlStatus.classifying: RETRY_AFTER_CLASSIFYING,
}


def _not_found(job_id: str, request_id: str) -> JSONResponse:
    """Standard 404 error envelope for missing jobs."""
    payload = ErrorEnvelope(
        error=ErrorPayload(
            code="not_found",
            message=f"Job '{job_id}' was not found.",
            request_id=request_id,
        )
    )
    return JSONResponse(status_code=404, content=payload.model_dump(mode="json"))


@router.get("/{job_id}", response_model=CrawlJob, status_code=status.HTTP_200_OK)
async def get_job(
    job_id: str,
    request: Request,
    response: Response,
    store: JobStore = Depends(get_job_store),
) -> CrawlJob | JSONResponse:
    """Get job status and metadata."""
    if not _is_valid_job_id(job_id):
        return _not_found(job_id, request.state.request_id)

    job = await store.get(job_id)
    if job is None:
        return _not_found(job_id, request.state.request_id)

    if job.status == CrawlStatus.queued:
        if job.submitted_at is not None:
            age_seconds = (datetime.now(UTC) - job.submitted_at).total_seconds()
            if age_seconds < _FRESH_JOB_GRACE_SECONDS:
                job = job.model_copy(update={"status": CrawlStatus.queued, "completed_at": None})

    if (
        job.status == CrawlStatus.done
        and job.error is None
        and await store.document_count(job_id) == 0
    ):
        job = job.model_copy(update={"status": CrawlStatus.queued, "completed_at": None})

    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Set Retry-After for all non-terminal states
    retry_after = _RETRY_AFTER_BY_STATUS.get(job.status)
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)

    return job


@router.get(
    "/{job_id}/documents",
    response_model=DocumentPageResponse,
    status_code=status.HTTP_200_OK,
)
async def get_job_documents(
    job_id: str,
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    doc_type: DocType | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    changed_only: bool = Query(default=False),
    store: JobStore = Depends(get_job_store),
) -> DocumentPageResponse | JSONResponse:
    """Get paginated documents for a job with optional filtering."""
    if not _is_valid_job_id(job_id):
        return _not_found(job_id, request.state.request_id)

    job = await store.get(job_id)
    if job is None:
        return _not_found(job_id, request.state.request_id)

    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    documents, next_cursor, has_more, total_available = await store.get_documents(
        job_id,
        cursor=cursor,
        limit=limit,
        doc_type=doc_type.value if doc_type else None,
        min_confidence=min_confidence,
    )
    return DocumentPageResponse(
        documents=documents,
        next_cursor=next_cursor,
        has_more=has_more,
        total_available=total_available,
    )


@router.post(
    "/{job_id}/cancel",
    response_model=CancelJobResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_job(
    job_id: str,
    request: Request,
    store: JobStore = Depends(get_job_store),
) -> CancelJobResponse | JSONResponse:
    """Cancel a running crawl job, salvaging any completed documents."""
    if not _is_valid_job_id(job_id):
        return _not_found(job_id, request.state.request_id)

    job = await store.get(job_id)
    if job is None:
        return _not_found(job_id, request.state.request_id)

    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    job = await store.cancel_job(job_id)

    return CancelJobResponse(
        job_id=job.job_id,
        status=job.status.value,
        documents_salvaged=await store.document_count(job_id),
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    request: Request,
    store: JobStore = Depends(get_job_store),
) -> Response:
    """Hard-delete a job and all its documents."""
    if not _is_valid_job_id(job_id):
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")

    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")

    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await store.delete(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
