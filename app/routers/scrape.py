from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.document import ScrapedDocument
from app.models.enums import ContentType, DocType
from app.models.requests import ScrapeRequest
from app.models.responses import AsyncJobResponse, ScrapeResponse
from app.services.job_store import JobStore

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
    if payload.mode == "async":
        job_id = await store.create_scrape_job(request.state.tenant_id)
        queued = AsyncJobResponse(job_id=job_id, status="queued")
        return JSONResponse(status_code=202, content=queued.model_dump(mode="json"))

    raw_text = "Hotararea nr. 125 privind aprobarea bugetului local."
    document = ScrapedDocument(
        document_id="d_stub_scrape",
        source_url=str(payload.url),
        canonical_url=None,
        mime_type="text/html",
        content_type=ContentType.html,
        raw_text=raw_text,
        raw_html=None,
        binary_url=None,
        doc_type=DocType.hcl,
        doc_type_confidence=0.94,
        title="HCL 125/2024",
        language="ro",
        published_at=None,
        page_count=None,
        content_length=len(raw_text),
        content_hash="sha256:stubhash",
        metadata={
            "discovered_at": datetime.now(UTC).isoformat(),
            "http_status": 200,
        },
        extraction_confidence=0.88,
        warnings=[],
    )

    return ScrapeResponse(
        request_id=request.state.request_id,
        document=document,
        latency_ms=1,
    )