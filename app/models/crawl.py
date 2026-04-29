# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Crawl job request/response models with SSRF validation."""

from __future__ import annotations

import ipaddress
import socket
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, StrictStr, field_validator

from app.models.enums import CrawlStatus, DocType, RenderMode

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_ssrf_url(url: str) -> bool:
    """Return True if *url* resolves to a private/loopback/link-local address."""
    try:
        parsed = urlparse(str(url))
        hostname = parsed.hostname or ""
        if not hostname:
            return True
        # DNS-based check mirrors the fetcher's runtime guard
        infos = socket.getaddrinfo(hostname, None)
        for *_, sockaddr in infos:
            try:
                addr = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            for net in _PRIVATE_NETS:
                if addr in net:
                    return True
    except Exception:
        pass
    return False


class CrawlAuth(BaseModel):
    type: Literal["basic", "cookie", "form"]
    credentials: dict[str, Any] = Field(default_factory=dict)


class CrawlConfig(BaseModel):
    seed_urls: list[HttpUrl] = Field(..., min_length=1, max_length=20)
    allowed_domains: list[str] = Field(default_factory=list)

    @field_validator("seed_urls")
    @classmethod
    def validate_ssrf(cls, v: list[HttpUrl]) -> list[HttpUrl]:
        for url in v:
            if _is_ssrf_url(str(url)):
                raise ValueError(f"Forbidden URL (private/loopback/link-local): {url}")
        return v

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def default_domains_from_seeds(cls, v: list[str], info: object) -> list[str]:
        """Spec §3.1: 'Empty = host of first seed'. Auto-populate if caller omits."""
        if v:
            return v
        # Extract hosts from seed_urls via the partially-validated data
        seeds = (info.data or {}).get("seed_urls", [])
        return list(dict.fromkeys(
            urlparse(str(u)).hostname or "" for u in seeds
            if urlparse(str(u)).hostname
        ))

    max_depth: int = Field(default=5, ge=1, le=20)
    max_pages: int = Field(default=2000, ge=1, le=100000)
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    doc_types_wanted: list[DocType] = Field(default_factory=list)
    respect_robots_txt: StrictBool = True
    max_requests_per_second: float = Field(default=1.0, ge=0.1, le=10.0)
    user_agent: str | None = None
    follow_pdfs: StrictBool = True
    max_pdf_size_mb: int = Field(default=50, ge=1)
    render_javascript: RenderMode = RenderMode.auto
    sitemap_hint_url: HttpUrl | None = None
    auth: CrawlAuth | None = None
    redact_pii: StrictBool = False


class IncrementalOptions(BaseModel):
    model_config = ConfigDict(strict=True)

    since: datetime | None = None
    previous_job_id: StrictStr | None = None
    known_content_hashes: list[str] = Field(default_factory=list)


class CrawlRequest(BaseModel):
    config: CrawlConfig
    incremental: IncrementalOptions | None = None
    callback_url: HttpUrl | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class CrawlProgress(BaseModel):
    stage: str
    urls_discovered: int = Field(..., ge=0)
    urls_fetched: int = Field(..., ge=0)
    documents_extracted: int = Field(..., ge=0)
    documents_classified: int = Field(..., ge=0)
    urls_pending: int = Field(..., ge=0)
    bytes_downloaded: int = Field(..., ge=0)


class CrawlStats(BaseModel):
    by_doc_type: dict[str, int] = Field(default_factory=dict)
    http_errors: dict[str, int] = Field(default_factory=dict)


class CrawlJob(BaseModel):
    job_id: str
    tenant_id: str
    status: CrawlStatus
    progress: CrawlProgress | None = None
    stats: CrawlStats | None = None
    config: CrawlConfig | None = None
    callback_url: HttpUrl | None = None
    submitted_at: datetime
    started_at: datetime | None = None
    estimated_completion_at: datetime | None = None
    completed_at: datetime | None = None
    error: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")
