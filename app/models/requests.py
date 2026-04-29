# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Inbound request models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool

from app.models.enums import DocType, RenderMode


class ScrapeRequest(BaseModel):
    url: HttpUrl
    render_javascript: RenderMode = RenderMode.auto
    follow_redirects: StrictBool = True
    include_raw_html: StrictBool = False
    classify: StrictBool = True
    extract_structured: StrictBool = False
    timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    mode: Literal["sync", "async"] = "sync"
    redact_pii: StrictBool = False


class ClassifyRequest(BaseModel):
    content: str
    url_hint: HttpUrl | None = None
    title_hint: str | None = None


class ExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    content: str
    doc_type: DocType
    schema_: dict[str, Any] = Field(alias="schema")