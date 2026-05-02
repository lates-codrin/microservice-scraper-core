# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""MIME type  ContentType mapping utility."""

from __future__ import annotations

from app.models.enums import ContentType


def content_type_from_mime(mime_type: str) -> ContentType:
    """Map a MIME type string to the ContentType enum."""
    normalized = mime_type.lower()
    if normalized == "application/pdf":
        return ContentType.pdf
    if normalized in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return ContentType.docx
    if normalized in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ):
        return ContentType.xlsx
    if normalized.startswith("image/"):
        return ContentType.image
    if normalized.startswith("text/html") or normalized == "application/xhtml+xml":
        return ContentType.html
    return ContentType.other


__all__ = ["content_type_from_mime"]
