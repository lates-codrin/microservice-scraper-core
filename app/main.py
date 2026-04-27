import os
import time

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware.auth_headers import AuthHeadersMiddleware
from app.models.common import ErrorEnvelope, ErrorPayload
from app.routers import classify, crawl, extract, health, jobs, openapi_spec, scrape
from app.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Lex-Advisor Scraper Service",
        version=settings.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.state.started_monotonic = time.monotonic()
    
    import redis
    app.state.redis = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True
    )

    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(AuthHeadersMiddleware, api_key=settings.api_key)
    app.add_middleware(RateLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "00000000-0000-4000-8000-000000000000")
        # Ensure all error parts are serializable
        safe_errors = []
        for err in exc.errors():
            safe_err = err.copy()
            if "input" in safe_err:
                safe_err["input"] = str(safe_err["input"])
            if "ctx" in safe_err:
                # ctx often contains the raw exception, convert to string
                safe_err["ctx"] = {k: str(v) for k, v in safe_err["ctx"].items()}
            safe_errors.append(safe_err)
            
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "request_id": request_id,
                    "details": {"errors": safe_errors}
                }
            },
            headers={"X-Request-ID": request_id}
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "00000000-0000-4000-8000-000000000000")
        code = "internal_error"
        if exc.status_code == 404: code = "not_found"
        elif exc.status_code == 403: code = "forbidden"
        elif exc.status_code == 401: code = "unauthorized"
        elif exc.status_code == 429: code = "rate_limited"
        
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorEnvelope(
                error=ErrorPayload(
                    code=code,
                    message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                    request_id=request_id
                )
            ).model_dump(mode="json"),
            headers={"X-Request-ID": request_id}
        )

    app.include_router(scrape.router)
    app.include_router(crawl.router)
    app.include_router(jobs.router)
    app.include_router(classify.router)
    app.include_router(extract.router)
    app.include_router(health.router)
    app.include_router(openapi_spec.router)

    return app


app = create_app()