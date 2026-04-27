from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.openapi_loader import load_provider_openapi

router = APIRouter(prefix="/v1", tags=["openapi"])


@router.get("/openapi.json", status_code=status.HTTP_200_OK)
def openapi_json() -> JSONResponse:
    return JSONResponse(content=load_provider_openapi())