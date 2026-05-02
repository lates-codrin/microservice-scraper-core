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

    match_num = re.search(r"(?:nr\.?|nr)\s*(\d+(?:/\d{4})?)", text, re.IGNORECASE)
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
        r"pentru:\s*(\d+).*?(?:împotrivă|impotriva):\s*(\d+).*?(?:abțineri|abtineri):\s*(\d+)",
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


def extract_dispozitie_primar_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Dispozitie (Mayoralty Decision)."""
    fields: dict[str, Any] = {
        "dispozitie_number": None,
        "issue_date": None,
    }
    confidence: dict[str, float] = {}
    match = re.search(r"(?:Disp|Dispoziție|Dispozitie)[.:]?\s*(\d+/\d{4})", text, re.IGNORECASE)
    if match:
        fields["dispozitie_number"] = match.group(1)
        confidence["dispozitie_number"] = 0.85
    return fields, confidence


def extract_act_normativ_local_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Act Normativ Local."""
    fields: dict[str, Any] = {"act_number": None}
    confidence: dict[str, float] = {}
    match = re.search(r"(?:nr|nr\.)\s*(\d+/\d{4})", text, re.IGNORECASE)
    if match:
        fields["act_number"] = match.group(1)
        confidence["act_number"] = 0.85
    return fields, confidence


def extract_proiect_hotarare_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Proiect Hotarare."""
    fields: dict[str, Any] = {"proposal_number": None}
    confidence: dict[str, float] = {}
    match = re.search(r"proiect[^0-9]*(\d+/\d{4})", text, re.IGNORECASE)
    if match:
        fields["proposal_number"] = match.group(1)
        confidence["proposal_number"] = 0.80
    return fields, confidence


def extract_regulament_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Regulament."""
    fields: dict[str, Any] = {"title": None}
    confidence: dict[str, float] = {}
    match = re.search(r"^(.{10,100})$", text, re.MULTILINE)
    if match:
        fields["title"] = match.group(1).strip()
        confidence["title"] = 0.70
    return fields, confidence


def extract_buget_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Buget."""
    fields: dict[str, Any] = {"budget_year": None, "currency": None}
    confidence: dict[str, float] = {}
    match = re.search(r"20\d{2}", text)
    if match:
        fields["budget_year"] = int(match.group(0))
        confidence["budget_year"] = 0.80
    if "lei" in text.lower() or "ron" in text.lower():
        fields["currency"] = "RON"
        confidence["currency"] = 0.95
    return fields, confidence


def extract_raport_executie_bugetara_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Raport Executie Bugetara."""
    return {}, {}


def extract_pug_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from PUG."""
    return {}, {}


def extract_puz_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from PUZ."""
    return {}, {}


def extract_strategie_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Strategie."""
    fields: dict[str, Any] = {"objectives_count": None}
    confidence: dict[str, float] = {}
    count = len(re.findall(r"obiectiv", text, re.IGNORECASE))
    if count > 0:
        fields["objectives_count"] = count
        confidence["objectives_count"] = 0.70
    return fields, confidence


def extract_organigrama_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Organigrama."""
    fields: dict[str, Any] = {"department_count": None}
    confidence: dict[str, float] = {}
    count = len(re.findall(r"departament|birou|serviciu", text, re.IGNORECASE))
    if count > 0:
        fields["department_count"] = count
        confidence["department_count"] = 0.70
    return fields, confidence


def extract_raport_activitate_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Raport Activitate."""
    fields: dict[str, Any] = {"activities_count": None}
    confidence: dict[str, float] = {}
    count = len(re.findall(r"activitate|acțiune|proiect", text, re.IGNORECASE))
    if count > 0:
        fields["activities_count"] = count
        confidence["activities_count"] = 0.70
    return fields, confidence


def extract_proces_verbal_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Proces Verbal."""
    fields: dict[str, Any] = {"decisions_count": None}
    confidence: dict[str, float] = {}
    count = len(re.findall(r"hotărâre|decizie|punct", text, re.IGNORECASE))
    if count > 0:
        fields["decisions_count"] = count
        confidence["decisions_count"] = 0.75
    return fields, confidence


def extract_consultare_publica_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Consultare Publica."""
    return {}, {}


def extract_anunt_public_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Anunt Public."""
    fields: dict[str, Any] = {"announcement_type": None}
    confidence: dict[str, float] = {}
    if any(word in text.lower() for word in ["licitație", "achizitie", "ofertă"]):
        fields["announcement_type"] = "procurement"
        confidence["announcement_type"] = 0.75
    return fields, confidence


def extract_anunt_achizitie_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Anunt Achizitie."""
    fields: dict[str, Any] = {"value": None}
    confidence: dict[str, float] = {}
    match = re.search(r"(\d+(?:,\d+)*)\s*(?:lei|ron|eur)", text, re.IGNORECASE)
    if match:
        fields["value"] = match.group(1)
        confidence["value"] = 0.75
    return fields, confidence


def extract_declaratie_avere_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from Declaratie Avere."""
    fields: dict[str, Any] = {"declaration_year": None}
    confidence: dict[str, float] = {}
    match = re.search(r"20\d{2}", text)
    if match:
        fields["declaration_year"] = int(match.group(0))
        confidence["declaration_year"] = 0.85
    return fields, confidence


def extract_other_fields(text: str) -> tuple[dict[str, Any], dict[str, float]]:
    """Extract fields from unclassified documents."""
    return {}, {}


def extract_fields(text: str, doc_type: DocType) -> tuple[dict[str, Any], dict[str, float]]:
    """Dispatch extraction by doc_type. Now supports all 18 doc_types."""
    extractors = {
        DocType.hcl: extract_hcl_fields,
        DocType.dispozitie_primar: extract_dispozitie_primar_fields,
        DocType.act_normativ_local: extract_act_normativ_local_fields,
        DocType.proiect_hotarare: extract_proiect_hotarare_fields,
        DocType.regulament: extract_regulament_fields,
        DocType.buget: extract_buget_fields,
        DocType.raport_executie_bugetara: extract_raport_executie_bugetara_fields,
        DocType.pug: extract_pug_fields,
        DocType.puz: extract_puz_fields,
        DocType.strategie: extract_strategie_fields,
        DocType.organigrama: extract_organigrama_fields,
        DocType.raport_activitate: extract_raport_activitate_fields,
        DocType.proces_verbal: extract_proces_verbal_fields,
        DocType.consultare_publica: extract_consultare_publica_fields,
        DocType.anunt_public: extract_anunt_public_fields,
        DocType.anunt_achizitie: extract_anunt_achizitie_fields,
        DocType.declaratie_avere: extract_declaratie_avere_fields,
        DocType.other: extract_other_fields,
    }

    extractor = extractors.get(doc_type, extract_other_fields)
    return extractor(text)


__all__ = ["extract_fields", "extract_hcl_fields"]
