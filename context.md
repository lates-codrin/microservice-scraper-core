# Scraper API Implementation Context

Last updated: 2026-04-27
Workspace root: c:/Users/lates/Desktop/microservice-scraper-core

## 1) Purpose of this file

This file is a working implementation snapshot for future AI sessions.
It records:
- current folder structure
- available local skills
- implementation status against the scraper API specs
- strict rules for validating any further changes

Use this file before making edits.

## 2) Source of truth

The API contract must be validated against both:
- scraper-api-spec.md (narrative requirements, constraints, non-functional requirements)
- scraper-api-spec.yaml (OpenAPI request/response schema and endpoint contracts)

If there is ambiguity, validate against both and preserve compatibility with the stricter interpretation.

## 3) Current folder structure

Top-level:
- .agents/
- .github/
- .env.example
- AGENTS.md
- Dockerfile (Hardened, Multi-stage, Pinned digest)
- docker-compose.yml (Full stack: API, Postgres, Redis, RabbitMQ, Test service)
- requirements.txt (Added schemathesis, hypothesis)
- pytest.ini
- scraper-api-spec.md
- scraper-api-spec.yaml
- README.md (New: Install, Env, Ops Runbook)
- app/
- tests/

App structure:
- app/main.py (Middleware registered)
- app/settings.py
- app/dependencies.py
- app/middleware/
  - auth_headers.py
  - rate_limit.py (New: RateLimit-* headers)
- app/models/ (Section 3 entities)
- app/routers/ (Section 4 endpoints)
- app/services/
  - job_store.py (Persistence, pagination, deduplication)
  - openapi_loader.py
  - fetcher.py (SSRF, robots.txt, rate-limiting)
  - extractor.py (HTML, PDF, OCR, diacritics)
  - classifier.py (Taxonomy)
- tests/
  - contract/ (New: Schemathesis, Domain tests, OpenAPI consistency)
  - test_browser_frontier.py
  - test_classifier.py
  - test_fetcher_extractor.py
  - test_health_smoke.py
  - test_incremental.py
  - test_jobs.py
  - test_webhooks.py

## 4) Local skills currently present

- caveman family, create-tasks, compress.

## 5) Current implementation status

### Done

- **Hardening Pass Complete**:
  - Dockerfile: Multi-stage build, pinned digests, non-root user (appuser:1000).
  - Rate Limiting: `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` headers on all responses. `Retry-After` on 429.
  - OpenAPI Consistency: `GET /v1/openapi.json` byte-for-byte identical to YAML (normalized). Added CI test.
  - Full Stack Compose: Includes Postgres, Redis, RabbitMQ, and automated test runner.
- **Contract & Domain Testing**:
  - `schemathesis`: Fuzzing all endpoints, validating status codes and required fields.
  - Diacritics: Verified Romanian char preservation (ș U+0219).
  - Incremental: Hash-based deduplication verified.
  - Cross-tenant Isolation: Enforced with 403 on tenant mismatch.
  - SSRF Protection: seed_url validation (rejection of 169.254.169.254).
  - Robots.txt: Compliance verified.
  - delivery: Webhook delivery with HMAC and retries.
- **Documentation**: Comprehensive `README.md` with installation, env-vars, and ops runbook.

### Next Steps

- Final verification of all tests passing in a clean environment.
- Optimize image size (ensure < 500 MB).
- Full end-to-end integration with target Romanian cityhall sites.

## 6) Non-negotiable implementation rules

1. Always read both scraper-api-spec.md and scraper-api-spec.yaml.
2. Maintain hardened Docker/Compose standards.
3. Keep RateLimit headers in every response.
4. Ensure 100% contract compliance via schemathesis.
5. Use caveman mode for token efficiency.

## 7) Required verification workflow

1. `docker compose run test` must exit 0.
2. `trivy image --severity CRITICAL,HIGH <image>` must be clean.
3. Verify `X-Request-ID` echo in all responses.
4. Verify `RateLimit-*` headers in all responses.

## 8) Fast command reference

- install: `python -m pip install -r requirements.txt`
- run tests: `python -m pytest tests`
- run service: `uvicorn app.main:app --host 0.0.0.0 --port 8080`