# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""POST /v1/extract ” structured field extraction endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.models.enums import DocType
from app.models.requests import ExtractRequest
from app.models.responses import ExtractResponse
from app.services.field_extractor import extract_fields

router = APIRouter(prefix="/v1", tags=["extract"])


@router.post(
    "/extract",
    response_model=ExtractResponse,
    status_code=status.HTTP_200_OK,
)
async def extract(
    payload: ExtractRequest,
    request: Request,
) -> ExtractResponse | JSONResponse:
    """Extract structured fields from document content."""
    request_id = getattr(request.state, "request_id", "unknown")

    if payload.doc_type != DocType.hcl:
        return JSONResponse(
            status_code=501,
            content={
                "error": {
                    "code": "not_implemented",
                    "message": "Only HCL extraction is supported",
                    "request_id": request_id,
                }
            },
        )

    fields, confidence = extract_fields(payload.content, payload.doc_type)
    missing = [key for key, value in fields.items() if value is None]

    return ExtractResponse(
        fields=fields,
        field_confidence=confidence,
        missing_fields=missing,
    )
