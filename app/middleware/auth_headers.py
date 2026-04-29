# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Authentication and required-header validation middleware."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.models.common import ErrorEnvelope, ErrorPayload

# Tenant slug must be printable ASCII only — no newlines, CRs, NUL bytes or
# other control characters that could enable header/Redis-key injection.
_SAFE_SLUG_RE = re.compile(r"^[\x21-\x7E]+$")
_PUBLIC_PATHS = {
    "/docs",
    "/redoc",
    "/docs/health",
    "/v1/docs",
    "/v1/redoc",
    "/v1/docs/health",
    "/v1/openapi.json",
    "/v1/health",
}


class AuthHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, api_key: str) -> None:
        super().__init__(app)
        self.api_key = api_key

    def _error_response(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> JSONResponse:
        payload = ErrorEnvelope(
            error=ErrorPayload(
                code=code,
                message=message,
                request_id=request_id,
                details=details or {},
            )
        )
        return JSONResponse(
            status_code=status_code,
            content=payload.model_dump(mode="json"),
            headers={"X-Request-ID": request_id},
        )

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        if request.url.path in _PUBLIC_PATHS:
            response = await call_next(request)
            return response

        incoming_request_id = request.headers.get("X-Request-ID")
        response_request_id = incoming_request_id or str(uuid4())

        authorization = request.headers.get("Authorization")
        tenant_id = request.headers.get("X-Tenant-ID")

        if not authorization or not authorization.startswith("Bearer "):
            return self._error_response(
                status_code=401,
                code="unauthorized",
                message="Authorization header must use Bearer token.",
                request_id=response_request_id,
            )

        token = authorization.replace("Bearer ", "", 1).strip()
        if not token:
            return self._error_response(
                status_code=401,
                code="unauthorized",
                message="Authorization Bearer token is missing.",
                request_id=response_request_id,
            )

        if self.api_key and token != self.api_key:
            return self._error_response(
                status_code=401,
                code="unauthorized",
                message="API key is invalid.",
                request_id=response_request_id,
            )

        if incoming_request_id is None:
            return self._error_response(
                status_code=400,
                code="invalid_request",
                message="X-Request-ID header is required.",
                request_id=response_request_id,
            )

        # Reject any control characters (newlines, CRs, etc.) before UUID parse —
        # prevents header-injection in the echoed X-Request-ID.
        if not _SAFE_SLUG_RE.match(incoming_request_id):
            return self._error_response(
                status_code=400,
                code="invalid_request",
                message="X-Request-ID contains invalid characters.",
                request_id=str(uuid4()),
                details={"header": "X-Request-ID"},
            )

        try:
            UUID(incoming_request_id)
        except ValueError:
            return self._error_response(
                status_code=400,
                code="invalid_request",
                message="X-Request-ID must be a valid UUID.",
                request_id=response_request_id,
                details={"header": "X-Request-ID"},
            )

        if not tenant_id or not tenant_id.strip():
            return self._error_response(
                status_code=403,
                code="forbidden",
                message="X-Tenant-ID header is required.",
                request_id=incoming_request_id,
            )

        # Reject control characters in X-Tenant-ID — prevents header injection
        # and Redis key injection (keys are built as "IDEM:{tenant_id}:...").
        if not _SAFE_SLUG_RE.match(tenant_id.strip()):
            return self._error_response(
                status_code=400,
                code="invalid_request",
                message="X-Tenant-ID contains invalid characters.",
                request_id=incoming_request_id,
                details={"header": "X-Tenant-ID"},
            )

        request.state.request_id = incoming_request_id
        request.state.tenant_id = tenant_id.strip()

        response = await call_next(request)
        response.headers["X-Request-ID"] = incoming_request_id
        response.headers["X-Vendor-Trace-ID"] = incoming_request_id  # mirrors request-id in absence of OTel
        # Server-Timing stub — populated per-endpoint when timing data is available
        if "Server-Timing" not in response.headers:
            response.headers["Server-Timing"] = "app;dur=0"
        return response
