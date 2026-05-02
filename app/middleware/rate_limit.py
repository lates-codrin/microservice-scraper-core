# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Rate limiting middleware - enforces Redis-backed per-tenant quotas."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Configurable via environment so tests can raise the ceiling without
# touching production defaults.
RATE_LIMIT = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))  # requests per window
RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed sliding-window rate limiting, scoped per tenant."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # ------------------------------------------------------------------
        # Resolve tenant from the request header.
        # request.state.tenant_id is never populated by any middleware, so
        # reading it always returned "unknown" and collapsed every tenant
        # into a single shared bucket.
        # ------------------------------------------------------------------
        tenant_id = request.headers.get("X-Tenant-ID", "unknown")

        redis = request.app.state.redis

        current_window = int(time.time() // RATE_WINDOW)
        rate_key = f"ratelimit:{tenant_id}:{current_window}"
        next_window_start = (current_window + 1) * RATE_WINDOW

        try:
            count = redis.incr(rate_key)
            if count == 1:
                # First hit in this window — attach a TTL so the key
                # auto-expires and doesn't accumulate forever.
                redis.expire(rate_key, RATE_WINDOW + 1)
        except Exception as exc:  # pragma: no cover
            logger.warning("Rate limit check failed (failing open): %s", exc)
            count = 0

        limit = RATE_LIMIT
        remaining = max(0, limit - count)

        # ------------------------------------------------------------------
        # Reject BEFORE calling downstream handlers.
        #    The original code called call_next first and then tried to
        #    overwrite response.status_code on the returned StreamingResponse,
        #    which has no effect — the status is already serialised.
        # ------------------------------------------------------------------
        if count > limit:
            logger.warning("Rate limit exceeded for tenant %s", tenant_id)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "RateLimit-Limit": str(limit),
                    "RateLimit-Remaining": "0",
                    "RateLimit-Reset": str(next_window_start),
                    "Retry-After": str(RATE_WINDOW),
                },
            )

        # ------------------------------------------------------------------
        # Happy path — forward the request and annotate the response.
        # ------------------------------------------------------------------
        response = await call_next(request)

        response.headers["RateLimit-Limit"] = str(limit)
        response.headers["RateLimit-Remaining"] = str(remaining)
        response.headers["RateLimit-Reset"] = str(next_window_start)

        return response
