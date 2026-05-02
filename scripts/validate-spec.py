#!/usr/bin/env python3
"""Validate the OpenAPI spec is syntactically correct."""

from pathlib import Path

import yaml

spec_path = Path("/vercel/share/v0-project/scraper-api-spec.yaml")

try:
    with spec_path.open("r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    print("[v0] OpenAPI spec is valid YAML")
    print(f"[v0] Title: {spec.get('info', {}).get('title')}")
    print(f"[v0] Version: {spec.get('info', {}).get('version')}")
    print(f"[v0] x-scalar-theme: {spec.get('info', {}).get('x-scalar-theme')}")
    print(f"[v0] Number of paths: {len(spec.get('paths', {}))}")
    print(
        f"[v0] Security schemes: {list(spec.get('components', {}).get('securitySchemes', {}).keys())}"
    )

    # Check for code samples on key endpoints
    scrape_samples = (
        spec.get("paths", {})
        .get("/v1/scrape", {})
        .get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("x-codeSamples")
    )
    crawl_samples = (
        spec.get("paths", {})
        .get("/v1/crawl", {})
        .get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("x-codeSamples")
    )

    print(f"[v0] /v1/scrape has {len(scrape_samples or [])} code samples")
    print(f"[v0] /v1/crawl has {len(crawl_samples or [])} code samples")

except Exception as e:
    print(f"[v0] Error validating spec: {e}")
    exit(1)
