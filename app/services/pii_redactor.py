# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""PII detection and redaction service."""

from __future__ import annotations

import re

# Pattern for Romanian personal ID numbers (CNP)
_CNP_PATTERN = re.compile(r"\b[1-8]\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{6}\b")

# Pattern for phone numbers (various formats)
_PHONE_PATTERN = re.compile(r"\b(?:\+?4)?(?:0|\+40)?[1-9]\d{8,9}\b")

# Pattern for email addresses
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# Pattern for credit card numbers
_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

# Common PII keywords (Romanian context)
_PII_KEYWORDS = {
    "ssn",
    "cnp",
    "pin",
    "password",
    "parola",
    "card number",
    "cartea de identitate",
}


def redact_pii(text: str) -> str:
    """Redact personally identifiable information from text.

    Redacts:
    - Romanian CNP numbers (personal ID)
    - Phone numbers
    - Email addresses
    - Credit card patterns
    """
    if not text:
        return text

    # Redact CNP numbers (Romanian personal ID)
    text = _CNP_PATTERN.sub("[REDACTED_CNP]", text)

    # Redact phone numbers
    text = _PHONE_PATTERN.sub("[REDACTED_PHONE]", text)

    # Redact email addresses
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)

    # Redact credit card patterns
    text = _CARD_PATTERN.sub("[REDACTED_CARD]", text)

    return text
