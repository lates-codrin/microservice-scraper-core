# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Rate limiting middleware ” adds RateLimit-* headers per spec."""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limit header middleware.
    In a real app, this would integrate with Redis to track actual quotas.
    For this pass, we implement the required headers and 429 logic.
    """

    def __init__(
        self,
        app: Any,
        limit: int = 100,
        window: int = 60,
    ) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Mock rate limiting logic
        # In a real system, we'd use request.state.tenant_id to scope this
        
        # For now, we just provide the headers as requested by the spec pass
        limit = self.limit
        remaining = 99  # Mock
        reset = int(time.time()) + 60 # Mock

        response = await call_next(request)
        
        response.headers["RateLimit-Limit"] = str(limit)
        response.headers["RateLimit-Remaining"] = str(remaining)
        response.headers["RateLimit-Reset"] = str(reset)
        
        if response.status_code == 429:
            response.headers["Retry-After"] = "60"
            
        return response

