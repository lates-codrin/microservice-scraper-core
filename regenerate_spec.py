#!/usr/bin/env python3
"""Regenerate OpenAPI spec from FastAPI app with custom metadata."""

from __future__ import annotations

import yaml

from app.main import create_app


def _parameter_ref(name: str) -> dict[str, str]:
    """Create a parameter reference."""
    return {"$ref": f"#/components/parameters/{name}"}


def _ensure_parameter_refs(operation: dict[str, object], names: list[str]) -> None:
    """Add parameter references to an operation if not already present."""
    parameters = operation.setdefault("parameters", [])
    if not isinstance(parameters, list):
        return

    existing_refs = {
        param.get("$ref") for param in parameters if isinstance(param, dict) and "$ref" in param
    }
    for name in names:
        ref = f"#/components/parameters/{name}"
        if ref not in existing_refs:
            parameters.append(_parameter_ref(name))


def _apply_openapi_overrides(spec: dict[str, object]) -> None:
    """Apply custom metadata and restore auth/header declarations."""
    # Info
    info = spec.setdefault("info", {})
    if isinstance(info, dict):
        info[
            "description"
        ] = """HTTP contract between the Lex-Advisor platform (caller) and any external
Scraper service (provider). Scraper discovers, fetches, and normalizes
documents from Romanian cityhall (primărie) websites so they can be
indexed by the RAG layer.

Any implementation — commercial vendor (Firecrawl, Apify, Zyte, Bright
Data), OSS fork, per-site Romanian freelancer build — that conforms
to this spec is a drop-in replacement.

Companion docs:
  - docs/external/scraper-api-spec.md (full narrative spec)"""
        info["contact"] = {
            "name": "Lex-Advisor Platform Team",
            "email": "costin@citydock.ro",
        }
        info["license"] = {"name": "Apache-2.0 WITH Commons-Clause-1.0"}
        info["x-scalar-theme"] = "purple"

    # Components: security schemes + parameters
    components = spec.setdefault("components", {})
    if not isinstance(components, dict):
        return

    security_schemes = components.setdefault("securitySchemes", {})
    if isinstance(security_schemes, dict):
        security_schemes.setdefault(
            "bearerAuth",
            {
                "type": "http",
                "scheme": "bearer",
                "description": "Static, per-tenant API key (≥ 256-bit entropy).",
            },
        )

    parameters = components.setdefault("parameters", {})
    if isinstance(parameters, dict):
        parameters.setdefault(
            "XRequestID",
            {
                "name": "X-Request-ID",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            },
        )
        parameters.setdefault(
            "XTenantID",
            {
                "name": "X-Tenant-ID",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "Caller's cityhall slug.",
            },
        )
        parameters.setdefault(
            "IdempotencyKey",
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            },
        )

    # Global security (applies to all endpoints unless overridden)
    spec["security"] = [{"bearerAuth": []}]

    # Add header parameters to specific endpoints
    paths = spec.setdefault("paths", {})
    if not isinstance(paths, dict):
        return

    shared = ["XRequestID", "XTenantID"]
    tenant_and_idem = ["XRequestID", "XTenantID", "IdempotencyKey"]

    operation_map: dict[tuple[str, str], list[str]] = {
        ("/v1/scrape", "post"): tenant_and_idem,
        ("/v1/crawl", "post"): tenant_and_idem,
        ("/v1/classify", "post"): shared,
        ("/v1/extract", "post"): shared,
        ("/v1/jobs/{job_id}", "get"): ["XTenantID"],
        ("/v1/jobs/{job_id}", "delete"): ["XTenantID"],
        ("/v1/jobs/{job_id}/documents", "get"): ["XTenantID"],
        ("/v1/jobs/{job_id}/cancel", "post"): ["XTenantID"],
        ("/v1/metrics", "get"): shared,
    }

    for (path, method), parameter_names in operation_map.items():
        path_item = paths.get(path)
        if not isinstance(path_item, dict):
            continue
        operation = path_item.get(method)
        if not isinstance(operation, dict):
            continue
        _ensure_parameter_refs(operation, parameter_names)

    # Public endpoints: no auth required
    for public_path, methods in {
        "/v1/health": ["get"],
        "/v1/openapi.json": ["get"],
    }.items():
        path_item = paths.get(public_path)
        if not isinstance(path_item, dict):
            continue
        for method in methods:
            operation = path_item.get(method)
            if isinstance(operation, dict):
                operation["security"] = []


# Generate fresh spec from app
app = create_app()
spec = app.openapi()

_apply_openapi_overrides(spec)

# Write both canonical spec files with readable YAML
for output_path in ("openapi.yaml", "scraper-api-spec.yaml"):
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

print("✓ YAML fully regenerated from FastAPI app with metadata")
