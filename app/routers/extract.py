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
    """Extract structured fields from document content.
    
    Supports all 18 doc_types:
    - hcl, dispozitie_primar, act_normativ_local, proiect_hotarare
    - regulament, buget, raport_executie_bugetara, pug, puz
    - strategie, organigrama, raport_activitate, proces_verbal
    - consultare_publica, anunt_public, anunt_achizitie
    - declaratie_avere, other
    """
    request_id = getattr(request.state, "request_id", "unknown")

    fields, confidence = extract_fields(payload.content, payload.doc_type)
    missing = [key for key, value in fields.items() if value is None]

    return ExtractResponse(
        fields=fields,
        field_confidence=confidence,
        missing_fields=missing,
    )
