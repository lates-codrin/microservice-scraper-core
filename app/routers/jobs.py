from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.common import ErrorEnvelope, ErrorPayload
from app.models.crawl import CrawlJob
from app.models.enums import CrawlStatus, DocType
from app.models.responses import CancelJobResponse, DocumentPageResponse
from app.services.job_store import JobStore

router = APIRouter(prefix="/v1/jobs", tags=["job"])


def _not_found(job_id: str, request_id: str) -> JSONResponse:
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
    job = await store.get(job_id)
    if job is None:
        return _not_found(job_id, request.state.request_id)
        
    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if job.status == CrawlStatus.queued:
        response.headers["Retry-After"] = "10"
    elif job.status == CrawlStatus.crawling:
        response.headers["Retry-After"] = "30"

    return job


@router.get("/{job_id}/documents", response_model=DocumentPageResponse, status_code=status.HTTP_200_OK)
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
    job = await store.get(job_id)
    if job is None:
        return _not_found(job_id, request.state.request_id)
        
    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if changed_only:
        # Stub behavior: changed_only is acknowledged but no filtering is applied yet.
        pass

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


@router.post("/{job_id}/cancel", response_model=CancelJobResponse, status_code=status.HTTP_200_OK)
async def cancel_job(
    job_id: str,
    request: Request,
    store: JobStore = Depends(get_job_store),
) -> CancelJobResponse | JSONResponse:
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
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")
        
    if job.tenant_id != request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    deleted = await store.delete(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)