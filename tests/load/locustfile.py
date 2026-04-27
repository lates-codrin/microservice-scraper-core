"""
Load baseline — simulates 10 concurrent users each:
  - Polling GET /v1/jobs/{job_id} every 5 s
  - Fetching GET /v1/jobs/{job_id}/documents pages

Targets:
  p95 < 200 ms for job poll
  p95 < 500 ms for document page

Run:
  locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 60s \
         --host http://localhost:5000 \
         --json > tests/load/baseline.json

Requires a running server with API_KEY=dev-api-key-change-me.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from locust import HttpUser, between, task, events

API_KEY = os.getenv("API_KEY", "dev-api-key-change-me")
TENANT = os.getenv("DEFAULT_TENANT_ID", "ph-balta-doamnei")

_BASE_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "X-Tenant-ID": TENANT,
}

_CRAWL_PAYLOAD = {
    "config": {
        "seed_urls": ["https://primaria-exemplu.ro"],
        "allowed_domains": ["primaria-exemplu.ro"],
        "max_depth": 1,
        "max_pages": 10,
    }
}


def _rid() -> str:
    return str(uuid.uuid4())


class ScraperAPIUser(HttpUser):
    wait_time = between(4, 6)  # ~5 s between tasks (mimics poll interval)

    job_id: str | None = None

    def on_start(self) -> None:
        """Create a crawl job to poll during the load test."""
        resp = self.client.post(
            "/v1/crawl",
            json=_CRAWL_PAYLOAD,
            headers={
                **_BASE_HEADERS,
                "X-Request-ID": _rid(),
                "Idempotency-Key": _rid(),
            },
        )
        if resp.status_code == 202:
            self.job_id = resp.json().get("job_id")
        else:
            self.job_id = None

    @task(3)
    def poll_job_status(self) -> None:
        """GET /v1/jobs/{job_id} — target p95 < 200 ms."""
        if not self.job_id:
            return
        self.client.get(
            f"/v1/jobs/{self.job_id}",
            headers={**_BASE_HEADERS, "X-Request-ID": _rid()},
            name="/v1/jobs/[job_id]",
        )

    @task(1)
    def fetch_documents_page(self) -> None:
        """GET /v1/jobs/{job_id}/documents — target p95 < 500 ms."""
        if not self.job_id:
            return
        self.client.get(
            f"/v1/jobs/{self.job_id}/documents?limit=100",
            headers={**_BASE_HEADERS, "X-Request-ID": _rid()},
            name="/v1/jobs/[job_id]/documents",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Baseline assertions (run after test via --json output)
# ─────────────────────────────────────────────────────────────────────────────


def assert_baseline(baseline_path: str = "tests/load/baseline.json") -> None:
    """Read Locust JSON output and assert p95 targets are met."""
    with open(baseline_path) as f:
        data = json.load(f)

    stats = {s["name"]: s for s in data.get("stats", [])}

    job_poll = stats.get("/v1/jobs/[job_id]", {})
    doc_page = stats.get("/v1/jobs/[job_id]/documents", {})

    job_p95 = job_poll.get("response_time_percentile_0.95", float("inf"))
    doc_p95 = doc_page.get("response_time_percentile_0.95", float("inf"))

    assert job_p95 < 200, f"Job poll p95={job_p95:.0f}ms exceeds 200ms target"
    assert doc_p95 < 500, f"Document page p95={doc_p95:.0f}ms exceeds 500ms target"
    print(f"✓ Job poll p95={job_p95:.0f}ms  Document page p95={doc_p95:.0f}ms")


if __name__ == "__main__":
    assert_baseline()
