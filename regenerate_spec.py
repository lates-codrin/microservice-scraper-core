#!/usr/bin/env python3
"""Regenerate OpenAPI spec from FastAPI app with custom metadata."""

import yaml
from app.main import create_app

# Generate fresh spec from app
app = create_app()
spec = app.openapi()

# Enhance the spec with our custom metadata
# Enhance the spec with our custom metadata (keep FastAPI's title as source of truth)
# spec['info']['title'] remains as FastAPI generates it

spec['info']['description'] = """HTTP contract between the Lex-Advisor platform (caller) and any external
Scraper service (provider). Scraper discovers, fetches, and normalizes
documents from Romanian cityhall (primărie) websites so they can be
indexed by the RAG layer.

Any implementation — commercial vendor (Firecrawl, Apify, Zyte, Bright
Data), OSS fork, per-site Romanian freelancer build — that conforms
to this spec is a drop-in replacement.

Companion docs:
  - docs/external/scraper-api-spec.md (full narrative spec)"""

spec['info']['contact'] = {
    'name': 'Lex-Advisor Platform Team',
    'email': 'costin@citydock.ro'
}
spec['info']['license'] = {
    'name': 'Apache-2.0 WITH Commons-Clause-1.0'
}
spec['info']['x-scalar-theme'] = 'purple'

# Write both canonical spec files with readable YAML
for output_path in ('openapi.yaml', 'scraper-api-spec.yaml'):
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

print('✓ YAML fully regenerated from FastAPI app with metadata')
