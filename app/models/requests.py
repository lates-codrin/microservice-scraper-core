from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.enums import DocType, RenderMode


class ScrapeRequest(BaseModel):
    url: HttpUrl
    render_javascript: RenderMode = RenderMode.auto
    follow_redirects: bool = True
    include_raw_html: bool = False
    classify: bool = True
    extract_structured: bool = False
    timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    mode: Literal["sync", "async"] = "sync"


class ClassifyRequest(BaseModel):
    content: str
    url_hint: HttpUrl | None = None
    title_hint: str | None = None


class ExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    content: str
    doc_type: DocType
    schema_: dict[str, Any] = Field(alias="schema")