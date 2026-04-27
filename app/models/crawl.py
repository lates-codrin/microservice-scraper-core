from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.enums import CrawlStatus, DocType, RenderMode


class CrawlAuth(BaseModel):
    type: str
    credentials: dict[str, Any] = Field(default_factory=dict)


class CrawlConfig(BaseModel):
    seed_urls: list[HttpUrl] = Field(..., min_length=1, max_length=20)
    allowed_domains: list[str]

    @field_validator("seed_urls")
    @classmethod
    def validate_ssrf(cls, v: list[HttpUrl]) -> list[HttpUrl]:
        forbidden = ["169.254.169.254", "localhost", "127.0.0.1"]
        for url in v:
            if any(f in str(url) for f in forbidden):
                raise ValueError(f"Forbidden URL: {url}")
        return v
    max_depth: int = Field(default=5, ge=1, le=20)
    max_pages: int = Field(default=2000, ge=1, le=100000)
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    doc_types_wanted: list[DocType] = Field(default_factory=list)
    respect_robots_txt: bool = True
    max_requests_per_second: float = Field(default=1.0, ge=0.1, le=10.0)
    user_agent: str | None = None
    follow_pdfs: bool = True
    max_pdf_size_mb: int = Field(default=50, ge=1)
    render_javascript: RenderMode = RenderMode.auto
    sitemap_hint_url: HttpUrl | None = None
    auth: CrawlAuth | None = None


class IncrementalOptions(BaseModel):
    since: datetime | None = None
    previous_job_id: str | None = None
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