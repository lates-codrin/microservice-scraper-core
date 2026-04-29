# Lex-Advisor Scraper Service

<div align="center">
  <h3>🔍 Documentation Preview</h3>
  <table border="0">
    <tr>
      <td>
        <p align="center"><b>API Swagger Docs</b></p>
        <img src="https://github.com/user-attachments/assets/5d958c1e-5b6c-42e6-acf0-8dd8f4fdf0c7" width="400px" />
      </td>
      <td>
        <p align="center"><b>Crawl Monitoring</b></p>
        <img src="https://github.com/user-attachments/assets/4bf0aa65-9d98-46c7-940b-afa624f6fcf9" width="400px" />
      </td>
    </tr>
    <tr>
      <td colspan="2" align="center">
        <p align="center"><b>System Architecture</b></p>
        <img src="https://github.com/user-attachments/assets/058508b0-4149-4464-bb50-251daa5485cd" width="600px" />
      </td>
    </tr>
  </table>
</div>

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

High-performance, hardened scraper microservice for Romanian municipal documents. Built with async Python, designed for multi-tenant production deployment.

## Features

- **Async Crawling** — BFS frontier with RabbitMQ queuing and Redis-backed progress tracking
- **JS Rendering** — Playwright Chromium pool with auto-detection of SPA shells
- **Multi-Format Extraction** — HTML (trafilatura), PDF (pdfplumber + OCR fallback), DOCX, XLSX
- **Document Classification** — Rule-based taxonomy for 18 Romanian municipal document types
- **Incremental Crawl** — Content-hash deduplication skips unchanged documents
- **Webhook Delivery** — HMAC-signed `X-Vendor-Signature` callbacks with exponential retry + DLQ
- **SSRF Hardened** — DNS resolution + IP blocklist on every outbound hop (fetcher, webhooks, seed URLs)
- **Production Docker** — Multi-stage build, non-root user, Playwright cached, Alembic auto-migration

## Quick Start

```bash
git clone <repo-url>
cd microservice-scraper-core
cp .env.example .env
docker compose up -d --build
```

The service is available at `http://localhost:8080`. API docs at `http://localhost:8080/docs`.

```bash
# Verify health
curl http://localhost:8080/v1/health

# Scrape a page
curl -X POST http://localhost:8080/v1/scrape \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.ro/hotarari", "classify": true}'
```

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | System overview, component responsibilities, state machine, data flow diagrams |
| [Configuration](docs/configuration.md) | Full environment variable reference with defaults |
| [API Examples](docs/api-examples.md) | Worked curl examples for every endpoint |
| [Security](docs/security.md) | Threat model, SSRF defence, injection hardening, CVE audit |
| [Operations](docs/ops-runbook.md) | Service management, maintenance procedures, failure diagnosis |
| [Contributing](docs/contributing.md) | Developer setup, code standards, PR checklist |

## Infrastructure

| Component | Image | Port | Purpose |
|---|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | 5432 | Job + document persistence |
| Redis 7 | `redis:7-alpine` | 6379 | Rate limiting, idempotency, caching |
| RabbitMQ 3.13 | `rabbitmq:3.13-management-alpine` | 5672 / 15672 | Crawl frontier + webhook delivery |

## Testing

```bash
# Full suite via Docker
docker compose run test

# Local
pytest tests -v

# Lint + type check
ruff check app/
mypy --strict app/
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/scrape` | Single URL scrape (sync/async) |
| `POST` | `/v1/crawl` | Multi-URL crawl job |
| `GET` | `/v1/jobs/{id}` | Poll job status |
| `GET` | `/v1/jobs/{id}/documents` | Paginated results |
| `POST` | `/v1/jobs/{id}/cancel` | Cancel running job |
| `DELETE` | `/v1/jobs/{id}` | Delete job and data |
| `POST` | `/v1/classify` | Document type classification |
| `POST` | `/v1/extract` | Structured field extraction |
| `GET` | `/v1/health` | Service health check |

<details>
<summary><strong>Spec Compliance Checklist</strong></summary>

- ✅ All 9 endpoints implemented per `scraper-api-spec.yaml`
- ✅ Required headers: `Authorization`, `X-Request-ID`, `X-Tenant-ID`, `Idempotency-Key`
- ✅ All 18 `doc_type` taxonomy slugs (§3.3) reachable in classifier
- ✅ Full status chain: `queued → fetching_sitemap → crawling → extracting → classifying → done`
- ✅ Terminal states: `done`, `failed`, `cancelled`, `partial`
- ✅ State machine enforcement (invalid transitions rejected)
- ✅ `Retry-After` headers on all non-terminal job states
- ✅ Standard error envelope on all error responses
- ✅ Webhook `X-Vendor-Signature: sha256=<hmac>` per §5
- ✅ SSRF defence on fetcher, seed URLs, and webhook delivery

</details>

## License

[Apache-2.0](LICENSE) — Copyright 2026 Lates Codrin-Gabriel
