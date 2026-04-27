#!/bin/bash
cd /vercel/share/v0-project

# Stage all changes
git add -A

# Create commit with comprehensive message
git commit -m "Add interactive API documentation with Scalar and ReDoc

Features:
- Mount Scalar at GET /docs with interactive UI and 'Try it' buttons
- Mount ReDoc at GET /redoc as read-only alternative
- Add GET /docs/health endpoint for Scalar sidebar status badge
- Keep raw spec at GET /v1/openapi.json (unchanged)

OpenAPI spec enrichment:
- Add x-scalar-theme: purple for branding
- Add examples for POST /v1/scrape and POST /v1/crawl using Romanian cityhall domains
- Add x-codeSamples (curl, python, javascript) for major endpoints
- Enhance query parameter descriptions with clear, helpful text

Configuration:
- Add DOCS_ENABLED environment variable (default: true)
- Disable documentation returns 404 when docs disabled
- Add DOCS_ENABLED to settings.py with boolean env helper

Testing:
- Add comprehensive test suite (tests/test_docs.py)
- Validate documentation endpoints return correct status/content
- Verify OpenAPI spec validity and example presence
- Test code sample languages and realistic data

Dependencies:
- Add scalar-rs for interactive API documentation
- Add openapi-spec-validator for spec validation

Files:
- app/routers/docs.py: New documentation endpoints router
- app/settings.py: Add DOCS_ENABLED configuration
- app/main.py: Register docs router
- requirements.txt: Add dependencies
- scraper-api-spec.yaml: Enrich with examples and theme
- tests/test_docs.py: Full test coverage
- API_DOCUMENTATION.md: Implementation summary"

# Show git status
echo "[v0] Git status after commit:"
git log --oneline -1
