# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Structured field extraction for specific document types."""

from __future__ import annotations

import re
from typing import Any

from app.models.enums import DocType


def extract_hcl_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract structured fields from an HCL (HotÄƒrÃ¢re Consiliu Local) document.

    Returns a (fields, field_confidence) tuple.
    """
    fields: dict[str, Any] = {
        "hcl_number": None,
        "adoption_date": None,
        "subject": None,
        "votes": None,
    }
    confidence: dict[str, float] = {}

    match_num = re.search(r"(\d+/\d{4})", text)
    if match_num:
        fields["hcl_number"] = match_num.group(1)
        confidence["hcl_number"] = 0.99

    match_date = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
    if match_date:
        parts = match_date.group(1).split(".")
        fields["adoption_date"] = f"{parts[2]}-{parts[1]}-{parts[0]}"
        confidence["adoption_date"] = 0.90

    match_subject = re.search(r"privind\s+([^\.]+)", text, re.IGNORECASE)
    if match_subject:
        fields["subject"] = match_subject.group(1).strip()
        confidence["subject"] = 0.85

    match_votes = re.search(
        r"pentru:\s*(\d+).*?Ã®mpotrivÄƒ:\s*(\d+).*?abÈ›ineri:\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    if match_votes:
        fields["votes"] = {
            "for": int(match_votes.group(1)),
            "against": int(match_votes.group(2)),
            "abstain": int(match_votes.group(3)),
        }
        confidence["votes"] = 0.95

    return fields, confidence


def extract_fields(
    text: str, doc_type: DocType
) -> tuple[dict[str, Any], dict[str, float]]:
    """Dispatch extraction by doc_type.

    Currently only HCL is supported; all others return empty results.
    """
    if doc_type == DocType.hcl:
        return extract_hcl_fields(text)
    return {}, {}


__all__ = ["extract_fields", "extract_hcl_fields"]

