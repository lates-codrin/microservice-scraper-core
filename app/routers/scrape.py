# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""POST /v1/scrape ” single-URL scrape endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.requests import ScrapeRequest
from app.models.responses import AsyncJobResponse, ScrapeResponse
from app.services.fetcher import FetchError
from app.services.job_store import JobStore
from app.services.scrape_service import execute_sync_scrape

router = APIRouter(prefix="/v1", tags=["scrape"])


@router.post(
    "/scrape",
    response_model=ScrapeResponse,
    responses={202: {"model": AsyncJobResponse}},
    status_code=status.HTTP_200_OK,
)
async def scrape_url(
    payload: ScrapeRequest,
    request: Request,
    store: JobStore = Depends(get_job_store),
    idempotency_key: UUID = Header(..., alias="Idempotency-Key"),
) -> ScrapeResponse | JSONResponse:
    """Scrape a single URL synchronously or queue it for async processing."""
    if payload.mode == "async":
        job_id = await store.create_scrape_job(
            request.state.tenant_id,
            request_payload=payload.model_dump(mode="json"),
        )
        queued = AsyncJobResponse(job_id=job_id, status="queued")
        return JSONResponse(status_code=202, content=queued.model_dump(mode="json"))

    try:
        document, latency_ms = await execute_sync_scrape(
            payload=payload,
            tenant_id=request.state.tenant_id,
            request_id=request.state.request_id,
            store=store,
            redis_client=request.app.state.redis,
        )
    except FetchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    return ScrapeResponse(
        request_id=request.state.request_id,
        document=document,
        latency_ms=latency_ms,
    )
