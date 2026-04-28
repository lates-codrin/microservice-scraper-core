# Contributing Guide

## Prerequisites

- **Docker Desktop** (Windows/macOS) — required for running the full stack
- **Python 3.12** — for local development, linting, and type checking
- **Git** — with conventional commits enforced

## Quick Start

```bash
# Clone
git clone <repo-url>
cd microservice-scraper-core

# Create env file
cp .env.example .env

# Start everything
docker compose up -d --build

# Verify health
curl http://localhost:8080/v1/health
```

## Development Workflow

### Local Python Setup (for linting/testing)

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Running Tests

```bash
# Full suite (Docker)
docker compose run test

# Local (requires running Postgres + Redis)
pytest tests -v

# Specific test file
pytest tests/test_jobs.py -v

# With coverage
pytest tests --cov=app --cov-report=term-missing
```

### Linting & Type Checking

```bash
# Lint
ruff check app/

# Auto-fix
ruff check app/ --fix

# Format
ruff format app/

# Type check
mypy --strict app/
```

## Code Standards

### Architecture Rules

1. **Routers** handle HTTP concerns only — no business logic
2. **Services** contain all business logic — injected via `Depends()`
3. **Models** are Pydantic schemas or SQLAlchemy ORM classes — no logic
4. **Constants** go in `app/constants.py` — no magic numbers in code
5. **Interfaces** defined in `app/interfaces.py` — services implement ABCs

### Style Rules

- Every `.py` file starts with copyright header:
  ```python
  # Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
  # SPDX-License-Identifier: Apache-2.0
  ```
- Every `__init__.py` has `__all__` exports
- All public functions have type annotations
- All public functions have docstrings
- No `print()` — use `logging` (will migrate to `structlog`)
- No `time.sleep()` in async code
- All route handlers are `async def`

### SOLID Principles

| Principle | Enforcement |
|---|---|
| **SRP** | One class/module = one reason to change |
| **OCP** | Classifier uses registry pattern; extractor dispatches by MIME |
| **LSP** | All services implement protocol ABCs |
| **ISP** | Small, focused interfaces in `app/interfaces.py` |
| **DIP** | Service injection via FastAPI `Depends()` |

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add PDF table extraction
fix: SSRF bypass via redirect chain
refactor: extract scrape logic from router to service
docs: add API examples for /v1/classify
test: add tenant isolation test for document endpoint
chore: update Pillow to fix CVE-2026-25990
```

Subject line ≤ 50 chars. Body only when "why" isn't obvious from the subject.

## File Structure

```
app/
├── __init__.py          # Package root
├── constants.py         # All magic numbers and strings
├── interfaces.py        # ABC protocols for services
├── settings.py          # Env var configuration
├── main.py              # FastAPI app factory
├── db.py                # SQLAlchemy async engine
├── dependencies.py      # Depends() providers
├── worker.py            # Background worker entry point
├── middleware/
│   ├── auth_headers.py  # Auth + header validation
│   └── rate_limit.py    # RateLimit-* headers
├── models/
│   ├── common.py        # Error envelope
│   ├── crawl.py         # Crawl job models + SSRF validator
│   ├── db.py            # SQLAlchemy ORM models
│   ├── document.py      # ScrapedDocument
│   ├── enums.py         # DocType, CrawlStatus, etc.
│   ├── requests.py      # Inbound request schemas
│   └── responses.py     # Outbound response schemas
├── routers/
│   ├── classify.py      # POST /v1/classify
│   ├── crawl.py         # POST /v1/crawl
│   ├── docs.py          # /docs, /redoc
│   ├── extract.py       # POST /v1/extract
│   ├── health.py        # GET /v1/health
│   ├── jobs.py          # Job CRUD endpoints
│   ├── openapi_spec.py  # GET /v1/openapi.json
│   └── scrape.py        # POST /v1/scrape
└── services/
    ├── browser.py       # Playwright pool
    ├── classifier.py    # Rule-based taxonomy
    ├── extractor.py     # HTML/PDF/DOCX/XLSX extraction
    ├── fetcher.py       # Async HTTP + SSRF
    ├── field_extractor.py # Structured field extraction
    ├── frontier.py      # BFS crawl via RabbitMQ
    ├── job_store.py     # Job persistence + state machine
    ├── mime_utils.py    # MIME type mapping
    ├── openapi_loader.py # YAML spec loader
    ├── scrape_service.py # Scrape orchestration
    ├── state_machine.py # Status transition enforcement
    └── webhooks.py      # HMAC webhook delivery
```

## Testing Strategy

| Layer | Test Type | Command |
|---|---|---|
| Unit | `pytest tests/test_*.py` | Individual service logic |
| Contract | `pytest tests/contract/` | Schemathesis fuzzing against OpenAPI spec |
| Integration | `docker compose run test` | Full stack with real dependencies |

## Pull Request Checklist

- [ ] `ruff check app/` passes
- [ ] `mypy --strict app/` passes (or documents why an ignore is needed)
- [ ] New code has tests
- [ ] Docstrings on all public functions
- [ ] Copyright header on all new `.py` files
- [ ] `__all__` updated if adding public symbols
- [ ] No magic numbers (use `app/constants.py`)
- [ ] Commit messages follow Conventional Commits
