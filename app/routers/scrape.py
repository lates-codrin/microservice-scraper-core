from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_job_store
from app.models.document import ScrapedDocument
from app.models.enums import ContentType, CrawlStatus, DocType, RenderMode
from app.models.requests import ScrapeRequest
from app.models.responses import AsyncJobResponse, ScrapeResponse
from app.services.classifier import classify_document, extract_hcl_fields
from app.services.extractor import extract
from app.services.fetcher import FetchError, fetch
from app.services.browser import render_page
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

    job_id = await store.create_scrape_job(request.state.tenant_id)

    try:
        fetch_result = await fetch(
            str(payload.url),
            follow_redirects=payload.follow_redirects,
            timeout_ms=payload.timeout_ms,
            redis=request.app.state.redis,
        )

        is_html = fetch_result.mime_type == "text/html"
        rendered_html = fetch_result.content
        final_url = fetch_result.final_url
        used_playwright = False
        if is_html:
            rendered_html, final_url, used_playwright = await render_page(
                final_url,
                raw_html_bytes=fetch_result.content,
                render_mode=payload.render_javascript.value,
                include_raw_html=payload.include_raw_html,
                timeout_ms=payload.timeout_ms,
            )

        extracted = extract(rendered_html, fetch_result.mime_type, final_url)
        doc_type = DocType.other
        doc_type_confidence = 0.40
        alternatives: list[dict[str, object]] = []
        if payload.classify:
            doc_type, doc_type_confidence, alternatives = classify_document(final_url, extracted.raw_text)

        metadata: dict[str, object] = {
            "discovered_at": datetime.now(UTC).isoformat(),
            "http_status": fetch_result.http_status,
            "render_javascript": payload.render_javascript.value,
            "used_playwright": used_playwright,
            "redirect_chain": fetch_result.redirect_chain,
            "fetch_warnings": fetch_result.warnings,
            "extraction_warnings": extracted.warnings,
        }

        if payload.extract_structured and doc_type == DocType.hcl:
            structured_fields, field_confidence = extract_hcl_fields(extracted.raw_text)
            metadata["structured_fields"] = structured_fields
            metadata["field_confidence"] = field_confidence

        document = ScrapedDocument(
            document_id=f"d_{uuid4().hex[:12]}",
            source_url=str(payload.url),
            canonical_url=extracted.canonical_url or final_url,
            mime_type=extracted.mime_type,
            content_type=_content_type_from_mime(extracted.mime_type),
            raw_text=extracted.raw_text,
            raw_html=rendered_html.decode("utf-8", errors="replace") if payload.include_raw_html else None,
            binary_url=None,
            doc_type=doc_type,
            doc_type_confidence=doc_type_confidence,
            title=extracted.title,
            language=extracted.language,
            published_at=extracted.published_at,
            page_count=extracted.page_count,
            content_length=extracted.content_length,
            content_hash=extracted.content_hash,
            metadata=metadata,
            extraction_confidence=doc_type_confidence,
            warnings=fetch_result.warnings + extracted.warnings,
        )

        await store.add_document(job_id, request.state.tenant_id, document)
        await store.update(job_id, status=CrawlStatus.done)

    except FetchError as exc:
        await store.update(job_id, status=CrawlStatus.failed, error={"code": exc.code, "message": str(exc)})
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    except Exception as exc:
        await store.update(job_id, status=CrawlStatus.failed, error={"code": "internal_error", "message": str(exc)})
        raise

    return ScrapeResponse(
        request_id=request.state.request_id,
        document=document,
        latency_ms=fetch_result.response_time_ms,
    )


def _content_type_from_mime(mime_type: str) -> ContentType:
    normalized = mime_type.lower()
    if normalized == "application/pdf":
        return ContentType.pdf
    if normalized in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return ContentType.docx
    if normalized in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ):
        return ContentType.xlsx
    if normalized.startswith("image/"):
        return ContentType.image
    if normalized.startswith("text/html") or normalized == "application/xhtml+xml":
        return ContentType.html
    return ContentType.other