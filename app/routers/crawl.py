# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""POST /v1/crawl ” initiate a multi-URL crawl job."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.common import ErrorEnvelope, ErrorPayload
from app.models.crawl import CrawlRequest
from app.models.responses import CrawlAcceptedResponse
from app.services.job_store import DuplicateJobError, JobStore

router = APIRouter(prefix="/v1", tags=["crawl"])


def _request_fingerprint(payload: CrawlRequest) -> str:
    """Deterministic hash of the request body for idempotency collision detection."""
    normalized = json.dumps(
        payload.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@router.post(
    "/crawl",
    response_model=CrawlAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_crawl(
    payload: CrawlRequest,
    request: Request,
    idempotency_key: UUID = Header(..., alias="Idempotency-Key"),
    store: JobStore = Depends(get_job_store),
) -> CrawlAcceptedResponse | JSONResponse:
    """Start a new crawl job. Returns 202 Accepted with job metadata."""
    try:
        job = await store.create_crawl_job(
            request.state.tenant_id,
            payload.config,
            idempotency_key=str(idempotency_key),
            request_fingerprint=_request_fingerprint(payload),
            incremental=payload.incremental,
            callback_url=payload.callback_url,
        )
    except DuplicateJobError as exc:
        envelope = ErrorEnvelope(
            error=ErrorPayload(
                code="duplicate_job",
                message="Idempotency-Key already used with different request body.",
                request_id=request.state.request_id,
                details={"existing_job_id": exc.existing_job_id},
            )
        )
        return JSONResponse(status_code=409, content=envelope.model_dump(mode="json"))

    return CrawlAcceptedResponse(
        job_id=job.job_id,
        status=job.status.value,
        submitted_at=job.submitted_at,
        estimated_completion_at=job.estimated_completion_at,
    )
