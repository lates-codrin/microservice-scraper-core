from __future__ import annotations

from fastapi import APIRouter, status

from app.models.enums import DocType
from app.models.requests import ClassifyRequest
from app.models.responses import ClassifyAlternative, ClassifyResponse

router = APIRouter(prefix="/v1", tags=["classify"])


@router.post("/classify", response_model=ClassifyResponse, status_code=status.HTTP_200_OK)
def classify(payload: ClassifyRequest) -> ClassifyResponse:
    from app.services.classifier import classify_document
    doc_type, confidence, alts = classify_document(payload.url_hint, payload.content)
    
    return ClassifyResponse(
        doc_type=doc_type,
        doc_type_confidence=confidence,
        language="ro",
        alternatives=[
            ClassifyAlternative(doc_type=a["doc_type"], confidence=a["confidence"])
            for a in alts
        ]
    )