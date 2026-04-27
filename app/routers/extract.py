from __future__ import annotations

import uuid
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.models.requests import ExtractRequest
from app.models.responses import ExtractResponse

router = APIRouter(prefix="/v1", tags=["extract"])


@router.post("/extract", response_model=ExtractResponse, status_code=status.HTTP_200_OK)
def extract(payload: ExtractRequest, request: Request) -> ExtractResponse | JSONResponse:
    from app.services.classifier import extract_hcl_fields
    from app.models.enums import DocType
    
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    if payload.doc_type != DocType.hcl:
        return JSONResponse(
            status_code=501, 
            content={
                "error": {
                    "code": "not_implemented", 
                    "message": "Only HCL extraction is supported", 
                    "request_id": request_id
                }
            }
        )
        
    fields, conf = extract_hcl_fields(payload.content)
    missing = [k for k, v in fields.items() if v is None]
    
    return ExtractResponse(
        fields=fields,
        field_confidence=conf,
        missing_fields=missing,
    )