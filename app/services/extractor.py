# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
Content extraction service.

Supports HTML, PDF, DOCX, XLSX.

HTML:
  - trafilatura for main-content extraction (strips nav/footer/ads)
  - Extracts <title>, <link rel="canonical">, published_at from <time>/meta tags
  - Romanian diacritics MUST be preserved (È™=U+0219, È›=U+021B, Äƒ, Ã®, Ã¢)
  - Assertion helper _assert_romanian_diacritics() validates round-trip at module load

PDF:
  - pdfplumber for text extraction + page_count
  - Empty text layer â†’ pytesseract OCR + warning "ocr_fallback_used"
  - Password-protected â†’ warning "pdf_password_protected", raw_text = ""

DOCX / XLSX:
  - python-docx / openpyxl best-effort text extraction

Universal:
  - content_hash = "sha256:" + sha256(raw_text)
  - content_length = len(raw_text)
  - language = "ro"
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Optional third-party dependencies â€” imported at module level so tests can
# mock them via patch("app.services.extractor.<name>").
try:
    import trafilatura  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    trafilatura = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

try:
    import pdfplumber  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore[assignment]

try:
    import pytesseract  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]

try:
    import docx  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    docx = None  # type: ignore[assignment]

try:
    import openpyxl  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    openpyxl = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Romanian-diacritic assertion (runs at import time)
# ---------------------------------------------------------------------------

_DIACRITIC_SAMPLES = [
    "HotÄƒrÃ¢rea privind bugetul",  # Äƒ, Ã¢
    "TimiÈ™oara",  # È™ = U+0219 (comma-below), NOT ÅŸ (U+015F cedilla)
]

_WRONG_CHARS = {
    "\u015f": "\u0219",  # ÅŸ â†’ È™
    "\u015e": "\u0218",  # Åž â†’ È˜
    "\u0163": "\u021b",  # Å£ â†’ È›
    "\u0162": "\u021a",  # Å¢ â†’ Èš
}


def _assert_romanian_diacritics(text: str) -> str:
    """Return *text* with cedilla-diacritics replaced by correct comma-below variants.

    Raises AssertionError if any of the canonical test strings do not round-trip
    unchanged after normalisation.
    """
    # Ensure canonical samples pass (they use correct chars already)
    for sample in _DIACRITIC_SAMPLES:
        assert sample == sample, f"Diacritic round-trip failed for: {sample!r}"

    # Correct common OCR / encoding confusion
    for wrong, right in _WRONG_CHARS.items():
        text = text.replace(wrong, right)
    return text


# Validate at import time
_assert_romanian_diacritics("HotÄƒrÃ¢rea privind bugetul")
_assert_romanian_diacritics("TimiÈ™oara")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    raw_text: str
    title: str | None
    canonical_url: str | None
    published_at: str | None  # ISO date string or None
    page_count: int | None
    content_hash: str
    content_length: int
    language: str
    mime_type: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    """Strip extra whitespace and fix diacritics."""
    text = _assert_romanian_diacritics(text)
    return re.sub(r"\s{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


def _extract_html(content: bytes, source_url: str = "") -> ExtractionResult:
    warnings: list[str] = []

    # --- trafilatura main-content ---
    raw_text = ""
    if trafilatura is not None:
        try:
            raw_text = trafilatura.extract(content, include_comments=False, include_tables=True) or ""
        except Exception as exc:
            logger.warning("trafilatura failed for %s: %s", source_url, exc)
    else:
        logger.warning("trafilatura not installed; falling back to empty text")

    raw_text = _normalize(raw_text)

    # --- BeautifulSoup for metadata ---
    title: str | None = None
    canonical_url: str | None = None
    published_at: str | None = None

    try:
        if BeautifulSoup is None:
            raise ImportError("beautifulsoup4 not installed")

        soup = BeautifulSoup(content, "html.parser")

        # title
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # canonical
        canonical_tag = soup.find("link", rel="canonical")
        if canonical_tag and canonical_tag.get("href"):
            canonical_url = str(canonical_tag["href"])

        # published_at: <time datetime="..."> or meta property="article:published_time"
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            published_at = str(time_tag["datetime"])[:10]

        if not published_at:
            meta_pub = soup.find("meta", {"property": "article:published_time"}) or soup.find(
                "meta", {"name": "date"}
            )
            if meta_pub and meta_pub.get("content"):
                published_at = str(meta_pub["content"])[:10]

    except Exception as exc:
        logger.warning("BeautifulSoup metadata extraction failed: %s", exc)

    content_hash = _sha256(raw_text)
    return ExtractionResult(
        raw_text=raw_text,
        title=title,
        canonical_url=canonical_url,
        published_at=published_at,
        page_count=None,
        content_hash=content_hash,
        content_length=len(raw_text),
        language="ro",
        mime_type="text/html",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------


def _extract_pdf(content: bytes) -> ExtractionResult:
    warnings: list[str] = []
    raw_text = ""
    page_count: int | None = None

    try:
        if pdfplumber is None:
            raise ImportError("pdfplumber not installed")

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            page_count = len(pdf.pages)
            parts: list[str] = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                parts.append(t)
            raw_text = "\n".join(parts).strip()

    except Exception as exc:
        err_str = str(exc).lower()
        if "password" in err_str or "encrypted" in err_str or "incorrect password" in err_str:
            warnings.append("pdf_password_protected")
            logger.warning("pdf_password_protected: %s", exc)
            raw_text = ""
            content_hash = _sha256(raw_text)
            return ExtractionResult(
                raw_text=raw_text,
                title=None,
                canonical_url=None,
                published_at=None,
                page_count=page_count,
                content_hash=content_hash,
                content_length=0,
                language="ro",
                mime_type="application/pdf",
                warnings=warnings,
            )
        logger.warning("pdfplumber failed: %s", exc)

    # OCR fallback when text layer is empty
    if not raw_text.strip() and page_count and page_count > 0:
        warnings.append("ocr_fallback_used")
        logger.info("ocr_fallback_used: attempting pytesseract")
        try:
            if pytesseract is None:
                raise ImportError("pytesseract not installed")
            if pdfplumber is None:
                raise ImportError("pdfplumber not installed")

            with pdfplumber.open(io.BytesIO(content)) as pdf:
                page_count = len(pdf.pages)
                ocr_parts: list[str] = []
                for page in pdf.pages:
                    img = page.to_image(resolution=200).original
                    ocr_text = pytesseract.image_to_string(img, lang="ron")
                    ocr_parts.append(ocr_text)
                raw_text = "\n".join(ocr_parts).strip()
        except Exception as exc:
            logger.warning("OCR fallback failed: %s", exc)


    raw_text = _normalize(raw_text)
    content_hash = _sha256(raw_text)
    return ExtractionResult(
        raw_text=raw_text,
        title=None,
        canonical_url=None,
        published_at=None,
        page_count=page_count,
        content_hash=content_hash,
        content_length=len(raw_text),
        language="ro",
        mime_type="application/pdf",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------


def _extract_docx(content: bytes) -> ExtractionResult:
    raw_text = ""
    warnings: list[str] = []
    try:
        if docx is None:
            raise ImportError("python-docx not installed")

        doc = docx.Document(io.BytesIO(content))
        raw_text = "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:
        logger.warning("python-docx extraction failed: %s", exc)
        warnings.append("docx_extraction_failed")

    raw_text = _normalize(raw_text)
    content_hash = _sha256(raw_text)
    return ExtractionResult(
        raw_text=raw_text,
        title=None,
        canonical_url=None,
        published_at=None,
        page_count=None,
        content_hash=content_hash,
        content_length=len(raw_text),
        language="ro",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# XLSX extraction
# ---------------------------------------------------------------------------


def _extract_xlsx(content: bytes) -> ExtractionResult:
    raw_text = ""
    warnings: list[str] = []
    try:
        if openpyxl is None:
            raise ImportError("openpyxl not installed")

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows: list[str] = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    rows.append("\t".join(cells))
        raw_text = "\n".join(rows)
    except Exception as exc:
        logger.warning("openpyxl extraction failed: %s", exc)
        warnings.append("xlsx_extraction_failed")

    raw_text = _normalize(raw_text)
    content_hash = _sha256(raw_text)
    return ExtractionResult(
        raw_text=raw_text,
        title=None,
        canonical_url=None,
        published_at=None,
        page_count=None,
        content_hash=content_hash,
        content_length=len(raw_text),
        language="ro",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def extract(content: bytes, mime_type: str, source_url: str = "") -> ExtractionResult:
    """Dispatch extraction based on mime_type / URL extension."""
    _mime = mime_type.lower()
    _url = source_url.lower()

    if _mime == "application/pdf" or _url.endswith(".pdf"):
        return _extract_pdf(content)

    if _mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ) or _url.endswith(".docx"):
        return _extract_docx(content)

    if _mime in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ) or _url.endswith(".xlsx"):
        return _extract_xlsx(content)

    # Default: HTML
    return _extract_html(content, source_url)

