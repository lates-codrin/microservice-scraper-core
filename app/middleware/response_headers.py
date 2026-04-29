# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Response header middleware: Server-Timing, Cache-Status, etc."""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ResponseHeadersMiddleware(BaseHTTPMiddleware):
    """Add X-Vendor-Cache-Status, Server-Timing, and other response headers."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Track timing and add response headers."""
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # X-Vendor-Cache-Status: HIT|MISS (always MISS for now; caching layer TODO)
        response.headers["X-Vendor-Cache-Status"] = "MISS"

        # Server-Timing: fetch;dur=X, render;dur=Y, etc.
        # For now, single component: total_duration
        response.headers["Server-Timing"] = f"total_duration;dur={elapsed_ms:.0f}"

        return response
