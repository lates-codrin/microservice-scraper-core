# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""FastAPI application factory and global exception handlers."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware.auth_headers import AuthHeadersMiddleware
from fastapi.middleware.cors import CORSMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.response_headers import ResponseHeadersMiddleware
from app.models.common import ErrorEnvelope, ErrorPayload
from app.routers import admin, classify, crawl, docs, extract, health, jobs, metrics, openapi_spec, scrape
from app.services.metrics import MetricsMiddleware, get_metrics
from app.services.otel import init_otel, init_instrumentors
from app.settings import settings
from app.services.otel_logging import configure_structured_logging

logger = logging.getLogger(__name__)

# Error code mapping for HTTP status codes
_HTTP_ERROR_CODES: dict[int, str] = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    429: "rate_limited",
}

class HeaderValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id")
        tenant_id = request.headers.get("x-tenant-id")
        idem_key = request.headers.get("idempotency-key")
        
        if req_id and ("\n" in req_id or "\r" in req_id):
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_request", "message": "Invalid X-Request-ID", "request_id": ""}})
        if tenant_id and ("\n" in tenant_id or "\r" in tenant_id):
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_request", "message": "Invalid X-Tenant-ID", "request_id": req_id or ""}})
        if idem_key and ("\n" in idem_key or "\r" in idem_key):
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_request", "message": "Invalid Idempotency-Key", "request_id": req_id or ""}})
            
        return await call_next(request)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    # Initialize OpenTelemetry tracing
    init_otel("lex-advisor-scraper")
    init_instrumentors()
    # Initialize structured logging with OTel trace context
    configure_structured_logging()

    application = FastAPI(
        title="Lex-Advisor Scraper Service API",
        version=settings.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        openapi_version="3.0.3",
    )

    application.state.started_monotonic = time.monotonic()

    # Redis connection ” fall back to fakeredis when unavailable
    try:
        import redis as redis_lib

        if settings.redis_url:
            redis_client = redis_lib.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            redis_client.ping()
            application.state.redis = redis_client
            logger.info("Redis connected: %s", settings.redis_url)
        else:
            raise ConnectionError("No REDIS_URL configured")
    except Exception as exc:
        logger.warning("Redis unavailable (%s), using fakeredis", exc)
        import fakeredis

        application.state.redis = fakeredis.FakeRedis(decode_responses=True)

    # Middleware stack (order matters ” outermost first)    application.add_middleware(MetricsMiddleware, metrics=get_metrics())    application.add_middleware(AuthHeadersMiddleware, api_key=settings.api_key)
    # Middleware stack (order matters — outermost first)
    application.add_middleware(HeaderValidationMiddleware)
    application.add_middleware(ResponseHeadersMiddleware)
    application.add_middleware(MetricsMiddleware, metrics=get_metrics())
    application.add_middleware(AuthHeadersMiddleware, api_key=settings.api_key)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://lexy.latescodrin.com"  # YES I GET IT I SHOULD USE ENV VARS FOR THIS
        ], # TODO: make this configurable via env vars hehe later on tho -- codrin
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic validation errors  422 with standard error envelope."""
        request_id = getattr(
            request.state,
            "request_id",
            "00000000-0000-4000-8000-000000000000",
        )
        safe_errors = []
        for err in exc.errors():
            safe_err = err.copy()
            if "input" in safe_err:
                safe_err["input"] = str(safe_err["input"])
            if "ctx" in safe_err:
                safe_err["ctx"] = {
                    k: str(v) for k, v in safe_err["ctx"].items()
                }
            safe_errors.append(safe_err)

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "request_id": request_id,
                    "details": {"errors": safe_errors},
                }
            },
            headers={"X-Request-ID": request_id},
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """HTTP exceptions  standard error envelope with code mapping."""
        request_id = getattr(
            request.state,
            "request_id",
            "00000000-0000-4000-8000-000000000000",
        )
        code = _HTTP_ERROR_CODES.get(exc.status_code, "internal_error")

        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorEnvelope(
                error=ErrorPayload(
                    code=code,
                    message=(
                        exc.detail
                        if isinstance(exc.detail, str)
                        else str(exc.detail)
                    ),
                    request_id=request_id,
                )
            ).model_dump(mode="json"),
            headers={"X-Request-ID": request_id},
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    application.include_router(scrape.router)
    application.include_router(crawl.router)
    application.include_router(jobs.router)
    application.include_router(classify.router)
    application.include_router(extract.router)
    application.include_router(health.router)
    application.include_router(metrics.router)
    application.include_router(openapi_spec.router)
    application.include_router(docs.router)
    application.include_router(admin.router)  # dev-only, guarded by DOCS_ENABLED

    return application


app = create_app()
