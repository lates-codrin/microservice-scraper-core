# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Centralised constants â€” no magic numbers or strings elsewhere in app/."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

# TTL for idempotency keys in Redis (seconds). 24 hours.
IDEMPOTENCY_KEY_TTL_SECONDS: int = 86_400

# Sentinel value stored in Redis while a job is being created.
IDEMPOTENCY_PENDING_SENTINEL: str = "PENDING"

# Maximum number of poll attempts waiting for a concurrent creator to finish.
IDEMPOTENCY_RACE_POLL_ATTEMPTS: int = 40

# Sleep between race-poll attempts (seconds).
IDEMPOTENCY_RACE_POLL_INTERVAL: float = 0.05

# ---------------------------------------------------------------------------
# Redis key prefixes
# ---------------------------------------------------------------------------

REDIS_PREFIX_IDEMPOTENCY: str = "IDEM"
REDIS_PREFIX_IDEMPOTENCY_FINGERPRINT: str = "IDEM:fp"
REDIS_PREFIX_JOB_KNOWN_HASHES: str = "JOB:known_hashes"
REDIS_PREFIX_JOB_RETENTION: str = "JOB:retention"
REDIS_PREFIX_JOB_EXPIRED: str = "JOB:expired"
REDIS_PREFIX_JOB_PAGES: str = "JOB:pages"
REDIS_PREFIX_JOB_VISITED: str = "JOB:visited"
REDIS_PREFIX_JOB_PROGRESS: str = "JOB:progress"
REDIS_PREFIX_DOMAIN_RATE: str = "DOMAIN:rate"
REDIS_PREFIX_DOMAIN_ROBOTS: str = "DOMAIN:robots"

# ---------------------------------------------------------------------------
# Job retention
# ---------------------------------------------------------------------------

# Retention window for completed job documents (seconds). 30 days.
JOB_RETENTION_TTL_SECONDS: int = 30 * 86_400

# ---------------------------------------------------------------------------
# Job ID prefixes
# ---------------------------------------------------------------------------

JOB_ID_PREFIX_CRAWL: str = "cj_"
JOB_ID_PREFIX_SCRAPE: str = "sj_"

# ---------------------------------------------------------------------------
# Retry-After header values (seconds) by job status
# ---------------------------------------------------------------------------

RETRY_AFTER_QUEUED: int = 10
RETRY_AFTER_FETCHING_SITEMAP: int = 15
RETRY_AFTER_CRAWLING: int = 30
RETRY_AFTER_EXTRACTING: int = 20
RETRY_AFTER_CLASSIFYING: int = 20

# ---------------------------------------------------------------------------
# Classifier confidence scores
# ---------------------------------------------------------------------------

# When both URL and keyword match the same doc_type.
CONFIDENCE_URL_AND_KEYWORD_MATCH: float = 0.94

# When only keyword matches.
CONFIDENCE_KEYWORD_ONLY: float = 0.80

# When only URL matches.
CONFIDENCE_URL_ONLY: float = 0.75

# Default (no match â†’ "other").
CONFIDENCE_DEFAULT: float = 0.40

# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------

# Maximum redirect hops.
FETCHER_MAX_REDIRECTS: int = 10

# Default timeout for outbound HTTP requests (milliseconds).
FETCHER_DEFAULT_TIMEOUT_MS: int = 30_000

# Default per-domain rate limit (requests/second).
FETCHER_DEFAULT_RATE_LIMIT: float = 1.0

# Default max PDF size (MiB).
FETCHER_DEFAULT_MAX_PDF_SIZE_MB: int = 50

# robots.txt cache TTL in Redis (seconds). 1 hour.
ROBOTS_TTL_SECONDS: int = 3_600

# Default User-Agent string.
DEFAULT_USER_AGENT: str = (
    "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)"
)

# ---------------------------------------------------------------------------
# Browser pool
# ---------------------------------------------------------------------------

# Default number of concurrent Playwright browser contexts.
DEFAULT_BROWSER_WORKERS: int = 4

# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

# HMAC signature header name per spec Â§5.
WEBHOOK_SIGNATURE_HEADER: str = "X-Vendor-Signature"

# Maximum retry attempts before moving to DLQ.
WEBHOOK_MAX_RETRIES: int = 3

# Exponential back-off delays (seconds) for each retry attempt.
WEBHOOK_RETRY_DELAYS: list[int] = [5, 25, 125]

# RabbitMQ exchange/queue names for webhooks.
WEBHOOK_EXCHANGE: str = "webhooks"
WEBHOOK_QUEUE: str = "webhooks"
WEBHOOK_DLX: str = "webhooks.dlx"
WEBHOOK_DLQ: str = "webhooks.dlq"

# RabbitMQ exchange for crawl frontier.
FRONTIER_EXCHANGE: str = "crawl"

# ---------------------------------------------------------------------------
# Webhook event names (spec Â§5)
# ---------------------------------------------------------------------------

EVENT_CRAWL_STARTED: str = "crawl.started"
EVENT_CRAWL_PROGRESS: str = "crawl.progress"
EVENT_CRAWL_COMPLETED: str = "crawl.completed"
EVENT_CRAWL_FAILED: str = "crawl.failed"
EVENT_CRAWL_CANCELLED: str = "crawl.cancelled"

# ---------------------------------------------------------------------------
# Estimated job completion offset (minutes from submission).
# ---------------------------------------------------------------------------

ESTIMATED_CRAWL_COMPLETION_MINUTES: int = 30
ESTIMATED_SCRAPE_COMPLETION_SECONDS: int = 30

# ---------------------------------------------------------------------------
# Rate limit middleware defaults
# ---------------------------------------------------------------------------

RATE_LIMIT_DEFAULT_LIMIT: int = 100
RATE_LIMIT_DEFAULT_WINDOW_SECONDS: int = 60

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

PAGINATION_DEFAULT_LIMIT: int = 100
PAGINATION_MAX_LIMIT: int = 500

__all__ = [
    "CONFIDENCE_DEFAULT",
    "CONFIDENCE_KEYWORD_ONLY",
    "CONFIDENCE_URL_AND_KEYWORD_MATCH",
    "CONFIDENCE_URL_ONLY",
    "DEFAULT_BROWSER_WORKERS",
    "DEFAULT_USER_AGENT",
    "ESTIMATED_CRAWL_COMPLETION_MINUTES",
    "ESTIMATED_SCRAPE_COMPLETION_SECONDS",
    "EVENT_CRAWL_CANCELLED",
    "EVENT_CRAWL_COMPLETED",
    "EVENT_CRAWL_FAILED",
    "EVENT_CRAWL_PROGRESS",
    "EVENT_CRAWL_STARTED",
    "FETCHER_DEFAULT_MAX_PDF_SIZE_MB",
    "FETCHER_DEFAULT_RATE_LIMIT",
    "FETCHER_DEFAULT_TIMEOUT_MS",
    "FETCHER_MAX_REDIRECTS",
    "FRONTIER_EXCHANGE",
    "IDEMPOTENCY_KEY_TTL_SECONDS",
    "IDEMPOTENCY_PENDING_SENTINEL",
    "IDEMPOTENCY_RACE_POLL_ATTEMPTS",
    "IDEMPOTENCY_RACE_POLL_INTERVAL",
    "JOB_ID_PREFIX_CRAWL",
    "JOB_ID_PREFIX_SCRAPE",
    "JOB_RETENTION_TTL_SECONDS",
    "PAGINATION_DEFAULT_LIMIT",
    "PAGINATION_MAX_LIMIT",
    "RATE_LIMIT_DEFAULT_LIMIT",
    "RATE_LIMIT_DEFAULT_WINDOW_SECONDS",
    "REDIS_PREFIX_DOMAIN_RATE",
    "REDIS_PREFIX_DOMAIN_ROBOTS",
    "REDIS_PREFIX_IDEMPOTENCY",
    "REDIS_PREFIX_IDEMPOTENCY_FINGERPRINT",
    "REDIS_PREFIX_JOB_EXPIRED",
    "REDIS_PREFIX_JOB_KNOWN_HASHES",
    "REDIS_PREFIX_JOB_PAGES",
    "REDIS_PREFIX_JOB_PROGRESS",
    "REDIS_PREFIX_JOB_RETENTION",
    "REDIS_PREFIX_JOB_VISITED",
    "RETRY_AFTER_CLASSIFYING",
    "RETRY_AFTER_CRAWLING",
    "RETRY_AFTER_EXTRACTING",
    "RETRY_AFTER_FETCHING_SITEMAP",
    "RETRY_AFTER_QUEUED",
    "ROBOTS_TTL_SECONDS",
    "WEBHOOK_DLQ",
    "WEBHOOK_DLX",
    "WEBHOOK_EXCHANGE",
    "WEBHOOK_MAX_RETRIES",
    "WEBHOOK_QUEUE",
    "WEBHOOK_RETRY_DELAYS",
    "WEBHOOK_SIGNATURE_HEADER",
]

