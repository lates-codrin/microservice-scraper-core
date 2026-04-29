# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""ScrapedDocument model — the core output entity."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.enums import ContentType, DocType


class ScrapedDocument(BaseModel):
    document_id: str
    source_url: HttpUrl
    canonical_url: HttpUrl | None = None
    mime_type: str
    content_type: ContentType
    raw_text: str
    raw_html: str | None = None
    binary_url: HttpUrl | None = None
    doc_type: DocType
    doc_type_confidence: float = Field(..., ge=0.0, le=1.0)
    title: str | None = None
    language: str
    published_at: date | None = None
    page_count: int | None = Field(default=None, ge=1)
    content_length: int = Field(..., ge=0)
    content_hash: str
    metadata: dict[str, Any]
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")