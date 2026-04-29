# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Outbound response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.document import ScrapedDocument
from app.models.enums import DocType


class ScrapeResponse(BaseModel):
    request_id: str
    document: ScrapedDocument
    latency_ms: int = Field(..., ge=0)


class AsyncJobResponse(BaseModel):
    job_id: str
    status: str


class CrawlAcceptedResponse(BaseModel):
    job_id: str
    status: str
    submitted_at: datetime
    estimated_completion_at: datetime | None = None


class DocumentPageResponse(BaseModel):
    documents: list[ScrapedDocument]
    next_cursor: str | None = None
    has_more: bool
    total_available: int = Field(default=0, ge=0)


class CancelJobResponse(BaseModel):
    job_id: str
    status: str
    documents_salvaged: int = Field(default=0, ge=0)


class ClassifyAlternative(BaseModel):
    doc_type: DocType
    confidence: float = Field(..., ge=0.0, le=1.0)


class ClassifyResponse(BaseModel):
    doc_type: DocType
    doc_type_confidence: float = Field(..., ge=0.0, le=1.0)
    language: str
    alternatives: list[ClassifyAlternative] = Field(default_factory=list)


class ExtractResponse(BaseModel):
    fields: dict[str, Any]
    field_confidence: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)


class HealthStatusResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: int = Field(..., ge=0)
    dependencies: dict[str, str]
    queue_depth: int = Field(..., ge=0)
    active_workers: int = Field(..., ge=0)