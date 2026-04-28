# Architecture

## System Overview

The Lex-Advisor Scraper Service is a high-performance, async Python microservice that fetches, extracts, classifies, and stores Romanian municipal documents.

```mermaid
graph TB
    subgraph Client
        API[API Client]
    end

    subgraph "Scraper Service"
        GW[FastAPI Gateway<br/>Auth · Rate Limit · Headers]
        SR[Scrape Router]
        CR[Crawl Router]
        JR[Jobs Router]
        CL[Classify Router]
        EX[Extract Router]
        HR[Health Router]
    end

    subgraph "Service Layer"
        SS[Scrape Service]
        JS[Job Store]
        FT[Fetcher]
        XT[Extractor]
        CF[Classifier]
        FE[Field Extractor]
        BR[Browser Pool]
        FR[Frontier]
        WH[Webhook Worker]
    end

    subgraph Infrastructure
        PG[(PostgreSQL)]
        RD[(Redis)]
        RQ[RabbitMQ]
    end

    API -->|HTTP| GW
    GW --> SR & CR & JR & CL & EX & HR

    SR --> SS
    SS --> FT & BR & XT & CF & FE
    SS --> JS
    CR --> JS
    JR --> JS

    JS --> PG
    JS --> RD
    FT --> RD
    FR --> RQ
    FR --> RD
    WH --> RQ
```

## Component Responsibilities

| Component | Module | SRP Scope |
|---|---|---|
| **Scrape Service** | `app/services/scrape_service.py` | Orchestrates single-URL scrape: fetch → render → extract → classify |
| **Job Store** | `app/services/job_store.py` | CRUD for jobs + documents, idempotency, pagination |
| **Fetcher** | `app/services/fetcher.py` | Async HTTP with SSRF guard, rate limit, robots.txt |
| **Extractor** | `app/services/extractor.py` | HTML/PDF/DOCX/XLSX → raw text + metadata |
| **Classifier** | `app/services/classifier.py` | Rule-based taxonomy for 18 Romanian doc types |
| **Field Extractor** | `app/services/field_extractor.py` | Structured field extraction (HCL numbers, dates, votes) |
| **Browser Pool** | `app/services/browser.py` | Playwright Chromium pool for JS rendering |
| **Frontier** | `app/services/frontier.py` | BFS crawl orchestration via RabbitMQ |
| **Webhook Worker** | `app/services/webhooks.py` | HMAC-signed callback delivery with retry + DLQ |
| **State Machine** | `app/services/state_machine.py` | Enforces valid job status transitions |

## State Machine

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> fetching_sitemap
    queued --> crawling
    queued --> done : scrape shortcut
    queued --> failed
    queued --> cancelled

    fetching_sitemap --> crawling
    fetching_sitemap --> failed
    fetching_sitemap --> cancelled

    crawling --> extracting
    crawling --> done
    crawling --> failed
    crawling --> cancelled
    crawling --> partial

    extracting --> classifying
    extracting --> done
    extracting --> failed
    extracting --> cancelled
    extracting --> partial

    classifying --> done
    classifying --> failed
    classifying --> cancelled
    classifying --> partial

    done --> [*]
    failed --> [*]
    cancelled --> [*]
    partial --> [*]
```

## Data Flow

### Sync Scrape (`POST /v1/scrape` with `mode=sync`)

1. **Auth middleware** validates `Authorization`, `X-Request-ID`, `X-Tenant-ID`
2. **Scrape router** delegates to **Scrape Service**
3. Service creates a scrape job (`sj_*`) in PostgreSQL
4. **Fetcher** resolves URL with SSRF checks on every redirect hop
5. **Browser Pool** renders JS if `render_javascript != never` and HTML looks like SPA
6. **Extractor** extracts text + metadata (trafilatura for HTML, pdfplumber for PDF)
7. **Classifier** assigns one of 18 `doc_type` slugs with confidence score
8. **Field Extractor** extracts structured fields (HCL only)
9. Document stored in PostgreSQL, job marked `done`
10. Response returned with `ScrapedDocument`

### Async Crawl (`POST /v1/crawl`)

1. Job created in `queued` state with idempotency protection (Redis `SETNX`)
2. **Frontier** seeds RabbitMQ queue from `seed_urls` + optional sitemap
3. Workers consume URLs from queue, apply URL filtering rules
4. Each URL processed: fetch → render → extract → enqueue child links
5. Redis tracks progress counters (`urls_discovered`, `urls_fetched`, etc.)
6. On completion, webhook delivered via HMAC-signed `X-Vendor-Signature`

## Infrastructure

| Component | Image | Purpose |
|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | Persistent storage for jobs and documents |
| Redis 7 | `redis:7-alpine` | Rate limiting, idempotency, job state, caching |
| RabbitMQ 3.13 | `rabbitmq:3.13-management-alpine` | Frontier URL queue + webhook delivery |

## Security Layers

See [security.md](security.md) for the full threat model.

| Layer | Implementation |
|---|---|
| Authentication | Bearer token in `Authorization` header |
| SSRF | DNS resolution + IP blocklist on every outbound hop |
| Tenant isolation | `X-Tenant-ID` enforced on all read/write operations |
| Idempotency | `Idempotency-Key` + `SETNX` prevents duplicate jobs |
| Injection | `_SAFE_SLUG_RE` rejects control characters in headers |
| Webhook SSRF | `follow_redirects=False` + IP blocklist on callback URLs |
