# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Prometheus metrics collection and exposition."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from starlette.types import ASGIApp, Receive, Scope, Send


@dataclass
class MetricsCollector:
    """Thread-safe Prometheus metrics collector."""

    _lock: Lock = field(default_factory=Lock)
    _http_requests_total: dict[tuple, int] = field(default_factory=lambda: defaultdict(int))
    _http_request_duration_seconds: dict[tuple, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _vendor_cost_usd_total: float = 0.0
    _vendor_tokens_total: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    _vendor_external_api_errors_total: dict[tuple, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _active_jobs: int = 0
    _documents_scraped_total: int = 0

    def record_http_request(
        self,
        method: str,
        status: int,
        endpoint: str,
        duration_seconds: float,
    ) -> None:
        """Record HTTP request metric."""
        with self._lock:
            key = (method, status, endpoint)
            self._http_requests_total[key] += 1
            self._http_request_duration_seconds[key].append(duration_seconds)

    def record_external_api_error(
        self,
        dependency: str,
        error_type: str,
    ) -> None:
        """Record external API error."""
        with self._lock:
            key = (dependency, error_type)
            self._vendor_external_api_errors_total[key] += 1

    def set_active_jobs(self, count: int) -> None:
        """Set current active job count."""
        with self._lock:
            self._active_jobs = count

    def record_document_scraped(self) -> None:
        """Increment documents scraped counter."""
        with self._lock:
            self._documents_scraped_total += 1

    def record_cost(self, usd: float) -> None:
        """Add to total cost."""
        with self._lock:
            self._vendor_cost_usd_total += usd

    def record_tokens(self, direction: str, count: int) -> None:
        """Record token usage."""
        with self._lock:
            self._vendor_tokens_total[direction] += count

    def render_prometheus(self) -> str:
        """Render metrics in Prometheus exposition format."""
        with self._lock:
            lines = ["# HELP http_requests_total Total HTTP requests", "# TYPE http_requests_total counter"]
            for (method, status, endpoint), count in self._http_requests_total.items():
                lines.append(
                    f'http_requests_total{{method="{method}",status="{status}",'
                    f'endpoint="{endpoint}"}} {count}'
                )

            lines.append("# HELP http_request_duration_seconds HTTP request latency")
            lines.append("# TYPE http_request_duration_seconds histogram")
            for (method, status, endpoint), durations in self._http_request_duration_seconds.items():
                if durations:
                    p50 = sorted(durations)[len(durations) // 2]
                    p95 = sorted(durations)[int(len(durations) * 0.95)]
                    p99 = sorted(durations)[int(len(durations) * 0.99)]
                    lines.append(
                        f'http_request_duration_seconds{{method="{method}",status="{status}",'
                        f'endpoint="{endpoint}",quantile="0.5"}} {p50}'
                    )
                    lines.append(
                        f'http_request_duration_seconds{{method="{method}",status="{status}",'
                        f'endpoint="{endpoint}",quantile="0.95"}} {p95}'
                    )
                    lines.append(
                        f'http_request_duration_seconds{{method="{method}",status="{status}",'
                        f'endpoint="{endpoint}",quantile="0.99"}} {p99}'
                    )

            lines.append("# HELP vendor_cost_usd_total Cumulative cost in USD")
            lines.append("# TYPE vendor_cost_usd_total counter")
            lines.append(f"vendor_cost_usd_total {self._vendor_cost_usd_total}")

            lines.append("# HELP vendor_tokens_total Total tokens consumed")
            lines.append("# TYPE vendor_tokens_total counter")
            lines.append(f'vendor_tokens_total{{direction="input"}} {self._vendor_tokens_total["input"]}')
            lines.append(f'vendor_tokens_total{{direction="output"}} {self._vendor_tokens_total["output"]}')

            lines.append("# HELP vendor_external_api_errors_total External API errors")
            lines.append("# TYPE vendor_external_api_errors_total counter")
            for (dependency, error_type), count in self._vendor_external_api_errors_total.items():
                lines.append(
                    f'vendor_external_api_errors_total{{dependency="{dependency}",'
                    f'error_type="{error_type}"}} {count}'
                )

            lines.append("# HELP active_jobs Current active crawl jobs")
            lines.append("# TYPE active_jobs gauge")
            lines.append(f"active_jobs {self._active_jobs}")

            lines.append("# HELP documents_scraped_total Total documents scraped")
            lines.append("# TYPE documents_scraped_total counter")
            lines.append(f"documents_scraped_total {self._documents_scraped_total}")

            return "\n".join(lines) + "\n"


# Global singleton
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    return _metrics


class MetricsMiddleware:
    """ASGI middleware to collect HTTP metrics."""

    def __init__(self, app: ASGIApp, metrics: MetricsCollector) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.monotonic()
        method = scope["method"]
        path = scope["path"]

        # Extract endpoint path (strip query string)
        endpoint = path.split("?")[0]

        status_code = 200

        async def send_with_metrics(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
        finally:
            duration = time.monotonic() - start_time
            self.metrics.record_http_request(method, status_code, endpoint, duration)
