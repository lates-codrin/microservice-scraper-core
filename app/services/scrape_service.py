# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Scrape orchestration service ” coordinates fetch  extract  classify."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.constants import CONFIDENCE_DEFAULT
from app.models.document import ScrapedDocument
from app.models.enums import CrawlStatus, DocType
from app.models.requests import ScrapeRequest
from app.services.browser import render_page
from app.services.classifier import classify_document
from app.services.extractor import extract
from app.services.fetcher import FetchError, fetch
from app.services.field_extractor import extract_hcl_fields
from app.services.job_store import JobStore
from app.services.mime_utils import content_type_from_mime
from app.services.pii_redactor import redact_pii as redact_pii_text

logger = logging.getLogger(__name__)


async def execute_sync_scrape(
    payload: ScrapeRequest,
    tenant_id: str,
    request_id: str,
    store: JobStore,
    redis_client: object,
    job_id: str | None = None,
) -> tuple[ScrapedDocument, int]:
    """Run a synchronous scrape and return (document, latency_ms).

    Raises FetchError on fetch failures.
    """
    if job_id is None:
        job_id = await store.create_scrape_job(
            tenant_id,
            request_payload=payload.model_dump(mode="json"),
            status=CrawlStatus.crawling,
        )

    try:
        fetch_result = await fetch(
            str(payload.url),
            follow_redirects=payload.follow_redirects,
            timeout_ms=payload.timeout_ms,
            redis=redis_client,
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
        doc_type_confidence = CONFIDENCE_DEFAULT
        if payload.classify:
            doc_type, doc_type_confidence, _alternatives = classify_document(
                final_url, extracted.raw_text
            )

        # Apply PII redaction if requested
        raw_text_final = extracted.raw_text
        if payload.redact_pii:
            raw_text_final = redact_pii_text(raw_text_final)

        metadata: dict[str, object] = {
            "discovered_at": datetime.now(UTC).isoformat(),
            "http_status": fetch_result.http_status,
            "render_javascript": payload.render_javascript.value,
            "used_playwright": used_playwright,
            "redirect_chain": fetch_result.redirect_chain,
            "fetch_warnings": fetch_result.warnings,
            "extraction_warnings": extracted.warnings,
            "pii_redacted": payload.redact_pii,
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
            content_type=content_type_from_mime(extracted.mime_type),
            raw_text=raw_text_final,
            raw_html=(
                rendered_html.decode("utf-8", errors="replace")
                if payload.include_raw_html
                else None
            ),
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

        await store.add_document(job_id, tenant_id, document)
        await store.update(job_id, status=CrawlStatus.done)

    except FetchError as exc:
        await store.update(
            job_id,
            status=CrawlStatus.failed,
            error={"code": exc.code, "message": str(exc)},
        )
        raise
    except Exception as exc:
        await store.update(
            job_id,
            status=CrawlStatus.failed,
            error={"code": "internal_error", "message": str(exc)},
        )
        raise

    return document, fetch_result.response_time_ms


__all__ = ["execute_sync_scrape"]
