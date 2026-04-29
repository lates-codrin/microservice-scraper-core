# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""GET /v1/openapi.json ” serve the canonical OpenAPI specification."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.openapi_loader import load_provider_openapi

router = APIRouter(prefix="/v1", tags=["openapi"])


@router.get("/openapi.json", status_code=status.HTTP_200_OK)
async def openapi_json() -> JSONResponse:
    """Serve the OpenAPI spec as JSON."""
    return JSONResponse(content=load_provider_openapi())
