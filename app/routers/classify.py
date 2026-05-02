# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""POST /v1/classify ” document type classification endpoint."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.models.requests import ClassifyRequest
from app.models.responses import ClassifyAlternative, ClassifyResponse
from app.services.classifier import classify_document

router = APIRouter(prefix="/v1", tags=["classify"])


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    status_code=status.HTTP_200_OK,
)
async def classify(payload: ClassifyRequest) -> ClassifyResponse:
    """For reclassifying existing documents without re-fetching."""
    url_hint = str(payload.url_hint) if payload.url_hint else None
    doc_type, confidence, alternatives = classify_document(url_hint, payload.content)

    return ClassifyResponse(
        doc_type=doc_type,
        doc_type_confidence=confidence,
        language="ro",
        alternatives=[
            ClassifyAlternative(doc_type=alt["doc_type"], confidence=alt["confidence"])
            for alt in alternatives
        ],
    )
