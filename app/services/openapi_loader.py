from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache(maxsize=1)
def load_provider_openapi() -> dict[str, Any]:
    spec_path = Path(__file__).resolve().parents[2] / "scraper-api-spec.yaml"
    if not spec_path.exists():
        raise FileNotFoundError(f"OpenAPI source file not found: {spec_path}")

    with spec_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise ValueError("OpenAPI source must parse to a JSON object.")

    return payload