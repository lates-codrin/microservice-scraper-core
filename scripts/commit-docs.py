#!/usr/bin/env python3
import os
import subprocess

os.chdir("/vercel/share/v0-project")

# Stage all changes
subprocess.run(["git", "add", "-A"], check=True)

# Create commit
commit_message = """Add interactive API documentation with Scalar and ReDoc

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
- Add openapi-spec-validator for spec validation"""

result = subprocess.run(["git", "commit", "-m", commit_message], capture_output=True, text=True)

if result.returncode == 0:
    print("[v0] Git commit successful")
    print(result.stdout)
else:
    print("[v0] Git commit output:")
    print(result.stdout)
    print(result.stderr)

# Show latest commit
result = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True, text=True)
print("[v0] Latest commit:")
print(result.stdout)
