# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Load and cache the OpenAPI specification from the YAML source file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache(maxsize=1)
def load_provider_openapi() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    # Prefer the delivery-spec filename; fall back to dev-time name
    for candidate in ("openapi.yaml", "scraper-api-spec.yaml"):
        spec_path = repo_root / candidate
        if spec_path.exists():
            break
    else:
        raise FileNotFoundError(f"OpenAPI source file not found in {repo_root}")

    with spec_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise ValueError("OpenAPI source must parse to a JSON object.")

    return payload