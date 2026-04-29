# Scraper Service — External API Specification

**Version:** `v1.0` · **Status:** Public vendor-facing specification · **Date:** 2026-04-22

## 0. Purpose

This document defines the HTTP contract between the Lex-Advisor platform
(caller) and any external Scraper service (provider). The scraper's job
is to discover, fetch, and normalize documents from Romanian cityhall
(primărie) websites so they can be indexed by the RAG layer (see
`docs/external/rag-api-spec.md`).

Any implementation — a commercial vendor (Firecrawl, Apify, Zyte,
Bright Data), an OSS fork, a per-site Romanian freelancer build — that
conforms to this spec is a drop-in replacement for the caller's scraper
layer.

The provider owns: URL discovery, HTTP fetching (with proxy, browser
fingerprint rotation, JS rendering, anti-bot evasion), content
extraction, MIME/doc-type classification, rate-limiting, robots.txt
compliance, incremental (delta) crawl state.

The caller owns: `cityhalls` table (tenant config, target URLs),
`sources` + `chunks` tables (indexed content), ingestion handoff to the
RAG service, admin UI, audit log, user-facing admin controls.

## 1. Conventions

- **Base URL:** configured per-deployment via `SCRAPER_API_URL` env var.
- **Transport:** HTTPS only, TLS ≥ 1.2.
- **Content-Type:** `application/json; charset=utf-8` unless noted.
- **Versioning:** URL-path (`/v1/...`). Breaking changes bump to `/v2/...`
  with ≥ 6-month overlap.
- **Region:** EU-only data residency (GDPR). Provider SHOULD co-locate
  with `europe-west3` (Frankfurt).
- **Timestamps:** ISO 8601 UTC with `Z` suffix.
- **IDs:** UUID v4 unless the spec says otherwise.
- **Tenant:** the caller's `cityhall_id` (slug, e.g. `ph-balta-doamnei`)
  scopes every operation. Provider MUST enforce hard isolation between
  tenants.

## 2. Authentication & Security

Every request MUST carry:

| Header | Type | Required | Purpose |
|---|---|---|---|
| `Authorization: Bearer <api_key>` | str | yes | Static, per-tenant API key (≥ 256-bit entropy). Rotatable. |
| `X-Request-ID` | UUID | yes | Echoed in response. Powers our audit trail. |
| `Idempotency-Key` | UUID | yes on `POST /v1/crawl` and `POST /v1/scrape` | Retries with the same key MUST return the same job. |
| `X-Tenant-ID` | str | yes | Our cityhall slug. Provider MUST scope all operations to this tenant. |

**Rate limit:** provider SHOULD advertise via `RateLimit-*` headers.
Caller backs off on `429`.

## 3. Data Models

### 3.1 `CrawlConfig`

```json
{
  "seed_urls": [
    "https://primaria-exemplu.ro/",
    "https://primaria-exemplu.ro/monitorul-oficial-local/"
  ],
  "allowed_domains": ["primaria-exemplu.ro", "primariaexemplu.ro"],
  "max_depth": 5,
  "max_pages": 2000,
  "include_patterns": [
    "/hcl/", "/dispozitii/", "/monitorul-oficial-local/",
    "/acte-normative/", "/consultare-publica/", "/proiecte-hotarari/"
  ],
  "exclude_patterns": [
    "/galerie-foto/", "/evenimente/", "\\.(jpg|png|gif|mp4)$"
  ],
  "doc_types_wanted": [
    "hcl", "dispozitie_primar", "act_normativ_local",
    "regulament", "buget", "pug", "puz", "consultare_publica"
  ],
  "respect_robots_txt": true,
  "max_requests_per_second": 1.0,
  "user_agent": "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)",
  "follow_pdfs": true,
  "max_pdf_size_mb": 50,
  "render_javascript": "auto",
  "sitemap_hint_url": "https://primaria-exemplu.ro/sitemap.xml",
  "auth": null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `seed_urls` | string[] | yes | 1-20 starting URLs. |
| `allowed_domains` | string[] | yes | Only URLs with these hosts are followed. Empty = host of first seed. |
| `max_depth` | int | optional | Default 5. Max link depth from any seed. |
| `max_pages` | int | optional | Default 2000. Hard cap on crawl size. |
| `include_patterns` | string[] | optional | URL regexes — if any match, page is in-scope. |
| `exclude_patterns` | string[] | optional | URL regexes — if any match, page is dropped. |
| `doc_types_wanted` | string[] | optional | Taxonomy in §3.3. Empty = all. Provider classifies + filters. |
| `respect_robots_txt` | bool | optional | Default `true`. |
| `max_requests_per_second` | float | optional | Default `1.0`. Per-domain. |
| `user_agent` | str | optional | Default provider's UA. |
| `follow_pdfs` | bool | optional | Default `true`. Download linked PDFs. |
| `max_pdf_size_mb` | int | optional | Default 50 MiB. Skip larger files. |
| `render_javascript` | str | optional | `"always"` \| `"never"` \| `"auto"` (default — provider decides per-page). |
| `sitemap_hint_url` | str \| null | optional | If site has sitemap.xml, use it to seed URLs. |
| `auth` | object \| null | optional | `{type: "basic" \| "cookie" \| "form", credentials: {...}}`. Rare for cityhalls. |

### 3.2 `ScrapedDocument`

```json
{
  "document_id": "d_7c3e9a1f...",
  "source_url": "https://primaria-exemplu.ro/hcl/2024/hcl-125-2024.pdf",
  "canonical_url": "https://primaria-exemplu.ro/hcl/hcl-125-2024",
  "mime_type": "application/pdf",
  "content_type": "pdf",
  "raw_text": "Hotărârea nr. 125 din 22.04.2024 privind aprobarea ...",
  "raw_html": null,
  "binary_url": "https://scraper.partner.example/storage/d_7c3e9a1f.pdf",
  "doc_type": "hcl",
  "doc_type_confidence": 0.94,
  "title": "HCL nr. 125/2024 privind aprobarea bugetului local",
  "language": "ro",
  "published_at": "2024-04-22",
  "page_count": 12,
  "content_length": 48210,
  "content_hash": "sha256:abc123...",
  "metadata": {
    "parent_url": "https://primaria-exemplu.ro/hcl/2024/",
    "discovered_at": "2026-04-22T10:15:33Z",
    "http_status": 200,
    "response_time_ms": 412,
    "redirect_chain": [],
    "headers": { "last-modified": "Mon, 22 Apr 2024 08:00:00 GMT" }
  },
  "extraction_confidence": 0.88,
  "warnings": []
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `document_id` | str | yes | Provider-generated, stable across crawls within one tenant. |
| `source_url` | str | yes | Actual URL fetched. |
| `canonical_url` | str \| null | optional | If page advertises `<link rel="canonical">`, echo it. |
| `mime_type` | str | yes | MIME of fetched content. |
| `content_type` | str | yes | Normalized: `html` \| `pdf` \| `docx` \| `xlsx` \| `image` \| `other`. |
| `raw_text` | str | yes | Cleaned text extraction. Romanian preserved with diacritics. No HTML tags. No boilerplate (nav, footer, ads). |
| `raw_html` | str \| null | optional | For HTML pages only. Post-render DOM if JS executed. |
| `binary_url` | str \| null | optional | Pre-signed URL to original file (PDF/docx) stored by provider, 24h expiry. Caller downloads for re-ingest scenarios. |
| `doc_type` | str | yes | Classification from §3.3 taxonomy. |
| `doc_type_confidence` | float | yes | 0.0-1.0. Low = send to caller for manual review. |
| `title` | str \| null | yes if extractable | Best-effort title (HCL number, law name, page `<title>`). |
| `language` | str | yes | ISO 639-1. `"ro"` expected. |
| `published_at` | str (ISO date) \| null | optional | If provider can extract publication date. |
| `page_count` | int \| null | yes for PDFs | 1-indexed. |
| `content_length` | int | yes | `len(raw_text)` in chars. |
| `content_hash` | str | yes | SHA-256 of `raw_text`, for delta detection. |
| `metadata` | object | yes | See example; free-form extensions allowed. |
| `extraction_confidence` | float | yes | Provider-computed quality signal. |
| `warnings` | string[] | optional | e.g. `["ocr_fallback_used", "pdf_password_protected"]`. |

### 3.3 `doc_type` Taxonomy (Romanian municipal)

Provider MUST classify into one of these values. Unknown → `"other"`.

| Slug | Description |
|---|---|
| `hcl` | Hotărâre Consiliu Local — local council decision |
| `dispozitie_primar` | Dispoziție primar — mayor's disposition |
| `act_normativ_local` | Act normativ local — local normative act |
| `proiect_hotarare` | Proiect de hotărâre — draft council decision (pre-vote) |
| `regulament` | Regulament — regulation |
| `buget` | Buget local — local budget |
| `raport_executie_bugetara` | Execuție bugetară — budget execution report |
| `pug` | Plan Urbanistic General |
| `puz` | Plan Urbanistic Zonal |
| `strategie` | Strategie de dezvoltare — development strategy |
| `organigrama` | Organigramă — organization chart |
| `raport_activitate` | Raport de activitate — activity report |
| `proces_verbal` | Proces verbal ședință — meeting minutes |
| `consultare_publica` | Consultare publică — public consultation |
| `anunt_public` | Anunț public — public announcement |
| `anunt_achizitie` | Anunț achiziție publică — procurement announcement |
| `declaratie_avere` | Declarație de avere / interese — wealth/interest declaration |
| `other` | Fallback |

### 3.4 `CrawlJob`

```json
{
  "job_id": "cj_9f8e7d6c...",
  "tenant_id": "ph-balta-doamnei",
  "status": "running",
  "progress": {
    "stage": "crawling",
    "urls_discovered": 1247,
    "urls_fetched": 823,
    "documents_extracted": 411,
    "documents_classified": 411,
    "urls_pending": 424,
    "bytes_downloaded": 94532110
  },
  "stats": {
    "by_doc_type": {
      "hcl": 184, "dispozitie_primar": 62, "regulament": 28,
      "buget": 4, "anunt_public": 53, "other": 80
    },
    "http_errors": { "404": 12, "403": 2, "timeout": 5 }
  },
  "config": { /* CrawlConfig echo */ },
  "submitted_at": "2026-04-22T10:00:00Z",
  "started_at": "2026-04-22T10:00:12Z",
  "estimated_completion_at": "2026-04-22T10:35:00Z",
  "completed_at": null,
  "error": null
}
```

**Status values:** `queued` → `fetching_sitemap` → `crawling` → `extracting`
→ `classifying` → `done`. Terminal: `done` \| `failed` \| `cancelled` \| `partial`.

### 3.5 `Error`

Same shape as the RAG spec's Error model:

```json
{
  "error": {
    "code": "invalid_seed_url",
    "message": "seed_urls[0] is not a valid HTTP(S) URL",
    "request_id": "a6f1c1c1-...",
    "details": { "seed_url": "ftp://bad" }
  }
}
```

**Standard error codes:**

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `invalid_request` | Malformed JSON / missing field. |
| 400 | `invalid_seed_url` | Seed URL fails validation. |
| 401 | `unauthorized` | Missing / bad API key. |
| 403 | `forbidden` | Tenant mismatch. |
| 403 | `robots_disallowed` | Robots.txt blocks target and `respect_robots_txt=true`. |
| 404 | `not_found` | Job does not exist. |
| 409 | `duplicate_job` | Idempotency-Key reused with different body. |
| 413 | `payload_too_large` | Config too big / too many seeds. |
| 415 | `unsupported_media_type` | Unexpected content-type on single-scrape. |
| 422 | `validation_error` | Semantically invalid (e.g. negative `max_depth`). |
| 429 | `rate_limited` | Backoff. `Retry-After` header set. |
| 451 | `site_blocked` | Target site legally blocks bots / WAF. |
| 500 | `internal_error` | Retry-safe with Idempotency-Key. |
| 502 | `upstream_error` | Target site unreachable. |
| 503 | `service_unavailable` | Provider overload. |
| 504 | `timeout` | Caller should retry. |

## 4. Endpoints

### 4.1 `POST /v1/scrape` — Single-URL Scrape (sync or async)

For one-off fetches (e.g. admin "test this URL" button, re-ingesting a
single document).

**Request:**

```http
POST /v1/scrape HTTP/1.1
Content-Type: application/json
Authorization: Bearer <key>
X-Request-ID: <uuid>
X-Tenant-ID: ph-balta-doamnei
Idempotency-Key: <uuid>

{
  "url": "https://primaria-exemplu.ro/hcl/hcl-125-2024",
  "render_javascript": "auto",
  "follow_redirects": true,
  "include_raw_html": false,
  "classify": true,
  "extract_structured": false,
  "timeout_ms": 30000,
  "mode": "sync"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `url` | str | yes | Target URL. |
| `render_javascript` | str | optional | `"always"` \| `"never"` \| `"auto"`. |
| `follow_redirects` | bool | optional | Default `true`. Max 10 hops. |
| `include_raw_html` | bool | optional | Default `false`. Saves bandwidth. |
| `classify` | bool | optional | Default `true`. Run `doc_type` classification. |
| `extract_structured` | bool | optional | Default `false`. If `true`, also call `/v1/extract` internally. |
| `timeout_ms` | int | optional | Default 30000. Max 120000. |
| `mode` | str | optional | `"sync"` (default) \| `"async"`. Sync: response ≤ timeout_ms. Async: returns job_id. |

**Response (200, sync):**

```json
{
  "request_id": "...",
  "document": { /* ScrapedDocument */ },
  "latency_ms": 2341
}
```

**Response (202, async):**

```json
{ "job_id": "sj_...", "status": "queued" }
```

**Errors:** `400`, `401`, `403`, `422`, `451`, `500`, `502`, `504`.

---

### 4.2 `POST /v1/crawl` — Start Site Crawl

**Request:**

```http
POST /v1/crawl HTTP/1.1
Content-Type: application/json
Authorization: Bearer <key>
X-Request-ID: <uuid>
X-Tenant-ID: ph-balta-doamnei
Idempotency-Key: <uuid>

{
  "config": { /* CrawlConfig */ },
  "incremental": {
    "since": "2026-04-15T00:00:00Z",
    "previous_job_id": "cj_previous...",
    "known_content_hashes": ["sha256:abc...", "sha256:def..."]
  },
  "callback_url": "https://api.lex-advisor.citydock.ro/webhooks/scraper",
  "priority": "normal"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `config` | CrawlConfig | yes | §3.1. |
| `incremental` | object \| null | optional | Delta crawl: return only NEW or CHANGED documents. |
| `incremental.since` | str | optional | Only pages modified after this UTC timestamp (if server exposes Last-Modified). |
| `incremental.previous_job_id` | str | optional | Provider looks up what we had last time and diffs. |
| `incremental.known_content_hashes` | string[] | optional | Provider skips documents whose `content_hash` is in this list. |
| `callback_url` | str \| null | optional | HMAC-signed POST when job completes (see §5). |
| `priority` | str | optional | `"low"` \| `"normal"` \| `"high"`. Default `"normal"`. |

**Response (202):**

```json
{
  "job_id": "cj_9f8e7d6c...",
  "status": "queued",
  "submitted_at": "2026-04-22T10:00:00Z",
  "estimated_completion_at": "2026-04-22T10:35:00Z"
}
```

**Idempotency:** same `Idempotency-Key` + same body → returns existing
`job_id`. Same key, different body → `409 duplicate_job`.

**Errors:** `400`, `401`, `403`, `413`, `422`, `429`, `500`.

---

### 4.3 `GET /v1/jobs/{job_id}` — Poll Job Status

```http
GET /v1/jobs/cj_9f8e7d6c... HTTP/1.1
Authorization: Bearer <key>
X-Tenant-ID: ph-balta-doamnei
```

**Response (200):** `CrawlJob` (§3.4).

**Polling contract:** provider SHOULD set `Retry-After` header on 200
responses with non-terminal status. Default: 10 s while `queued`, 30 s
while `crawling`.

---

### 4.4 `GET /v1/jobs/{job_id}/documents` — Fetch Results (paginated)

```http
GET /v1/jobs/cj_9f8e7d6c.../documents?cursor=<opaque>&limit=100&min_confidence=0.5 HTTP/1.1
Authorization: Bearer <key>
X-Tenant-ID: ph-balta-doamnei
```

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `cursor` | str \| null | null | Opaque pagination token. |
| `limit` | int | 100 | Max 500. |
| `doc_type` | str | null | Filter by `doc_type` slug. |
| `min_confidence` | float | 0.0 | Drop documents below this `doc_type_confidence`. |
| `changed_only` | bool | false | On incremental crawls: only docs new/changed vs baseline. |

**Response (200):**

```json
{
  "documents": [ /* ScrapedDocument[] */ ],
  "next_cursor": "eyJvZmZzZXQiOiAxMDB9",
  "has_more": true,
  "total_available": 411
}
```

**Retention:** provider MUST retain documents at least 30 days after job
`done`. After that, return `410 gone` on fetch (caller should have
downloaded by then).

**Errors:** `400`, `401`, `403`, `404`, `410`.

---

### 4.5 `POST /v1/jobs/{job_id}/cancel` — Cancel Running Job

**Request:** body optional. **Response (200):**

```json
{ "job_id": "...", "status": "cancelled", "documents_salvaged": 237 }
```

Documents extracted before cancel are still retrievable via `/documents`.

---

### 4.6 `DELETE /v1/jobs/{job_id}` — Purge Job Data (GDPR)

Removes all extracted documents + metadata for this job.

**Response (204 No Content).** SLA: ≤ 24 h propagation.

---

### 4.7 `POST /v1/classify` — Standalone Classification

For reclassifying existing documents without re-fetching.

**Request:**

```json
{
  "content": "Hotărârea nr. 125 din 22.04.2024 privind aprobarea ...",
  "url_hint": "https://primaria-exemplu.ro/hcl/hcl-125-2024",
  "title_hint": "HCL 125/2024"
}
```

**Response (200):**

```json
{
  "doc_type": "hcl",
  "doc_type_confidence": 0.94,
  "language": "ro",
  "alternatives": [
    { "doc_type": "proiect_hotarare", "confidence": 0.04 }
  ]
}
```

---

### 4.8 `POST /v1/extract` — Structured Field Extraction (optional)

For documents where caller wants structured fields (e.g. HCL number,
date adopted, vote count).

**Request:**

```json
{
  "content": "Hotărârea nr. 125 din 22.04.2024 ...",
  "doc_type": "hcl",
  "schema": {
    "hcl_number": { "type": "string", "pattern": "^\\d+/\\d{4}$" },
    "adoption_date": { "type": "string", "format": "date" },
    "subject": { "type": "string", "maxLength": 500 },
    "votes": {
      "type": "object",
      "properties": {
        "for": { "type": "integer" },
        "against": { "type": "integer" },
        "abstain": { "type": "integer" }
      }
    }
  }
}
```

**Response (200):**

```json
{
  "fields": {
    "hcl_number": "125/2024",
    "adoption_date": "2024-04-22",
    "subject": "aprobarea bugetului local pentru anul 2024",
    "votes": { "for": 13, "against": 2, "abstain": 1 }
  },
  "field_confidence": {
    "hcl_number": 0.99, "adoption_date": 0.97,
    "subject": 0.85, "votes": 0.72
  },
  "missing_fields": []
}
```

**Optional endpoint** — if provider doesn't implement, caller will handle
structured extraction on its own side.

---

### 4.9 `GET /v1/health` — Liveness

```json
{
  "status": "ok",
  "version": "1.2.3",
  "uptime_seconds": 123456,
  "dependencies": {
    "proxy_pool": "ok",
    "browser_cluster": "ok",
    "storage": "ok",
    "classifier": "ok"
  },
  "queue_depth": 18,
  "active_workers": 24
}
```

## 5. Webhooks

Recommended — lets provider push completion instead of caller polling.

**Callback URL:** supplied in `POST /v1/crawl` via `callback_url`.

**Delivery:** `POST` with JSON body + `X-Vendor-Signature: sha256=<hmac>`
(HMAC-SHA256 of raw body using a shared secret — exchanged out of band).

**Body:**

```json
{
  "event": "crawl.completed",
  "job_id": "cj_...",
  "tenant_id": "ph-balta-doamnei",
  "status": "done",
  "stats": {
    "urls_fetched": 1247,
    "documents_extracted": 411,
    "by_doc_type": { "hcl": 184, "...": "..." }
  },
  "at": "2026-04-22T10:34:12Z"
}
```

**Events:**

- `crawl.started`
- `crawl.progress` (optional, every N documents — batch don't stream)
- `crawl.completed` / `crawl.failed` / `crawl.cancelled`
- `document.discovered` (optional, high-volume — only enable on request)
- `document.extracted` (optional, high-volume)

**Retry policy:** exponential backoff up to 24 h on non-2xx caller
response. Caller returns `200` on success.

## 6. Non-Functional Requirements

### 6.1 Performance

| Metric | Target (SLO) | Hard floor |
|---|---|---|
| `POST /v1/scrape` sync p95 (simple HTML) | ≤ 3,000 ms | ≤ 10,000 ms |
| `POST /v1/scrape` sync p95 (JS-rendered) | ≤ 15,000 ms | ≤ 30,000 ms |
| `POST /v1/scrape` sync p95 (PDF ≤ 10MB) | ≤ 20,000 ms | ≤ 60,000 ms |
| `POST /v1/crawl` accept | ≤ 500 ms (202) | — |
| Typical cityhall crawl (2,000 pages) | ≤ 45 min | ≤ 2 h |
| `GET /v1/jobs/{id}` p95 | ≤ 200 ms | ≤ 500 ms |
| `GET /v1/jobs/{id}/documents` p95 | ≤ 800 ms | ≤ 2,000 ms |
| `DELETE /v1/jobs/{id}` | ≤ 24 h end-to-end | ≤ 48 h |
| Uptime (monthly) | 99.5 % | 99.0 % |

### 6.2 Concurrency & Throughput

- **Concurrent jobs per tenant:** ≥ 3.
- **Total pages per day per tenant:** ≥ 50,000 (enough for monthly
  re-crawl of 10 cityhalls × 2,000 pages × 2.5 safety margin).
- **Provider self-throttles target site to `max_requests_per_second`
  per domain** regardless of concurrent jobs.

### 6.3 Quality Gate (Romanian municipal)

Before go-live, provider MUST pass caller's eval set (20 curated Romanian
cityhall targets, provided during onboarding):

- ≥ 90 % URL discovery recall on a curated list of 20 known-good HCL /
  dispozitie URLs per cityhall
- ≥ 85 % content extraction precision (hand-graded on 100 pages: is the
  extracted text the actual law body and nothing else?)
- ≥ 80 % `doc_type` classification accuracy vs human labels
- ≥ 95 % Romanian diacritic preservation (`ă ș ț î â` not mangled)
- p95 latency within 50 % of spec floor

### 6.4 Politeness & Legal

- **robots.txt:** honored when `respect_robots_txt=true` (default).
- **User-Agent:** MUST identify as a bot + include contact URL.
- **Rate limit:** respect `Retry-After` on 429 / 503 from targets.
- **Crawl-Delay:** honor the robots.txt directive if present.
- **No circumvention of auth/paywalls** unless `auth` is configured.
- **EU data residency:** all storage in EU region.
- **GDPR:** public government documents are public data, but any
  personal data incidentally captured (names, CNPs in declarații de
  avere) MUST be handled per GDPR — see §7.3.

## 7. Security

### 7.1 Transport & Auth
- TLS 1.2+, HSTS preload recommended.
- API keys ≥ 256-bit entropy, rotatable without downtime.
- Per-tenant key scoping — cross-tenant data access = P0 bug.

### 7.2 Input Validation
- Seed URLs MUST be HTTP/HTTPS only. No `file://`, `ftp://`, `gopher://`.
- Allowed domains validated as FQDNs.
- SSRF protection: provider MUST refuse to fetch internal IPs
  (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16,
  localhost, cloud metadata endpoints).
- Regex patterns in include/exclude validated to prevent ReDoS.

### 7.3 PII Handling
- Provider MAY redact obvious CNPs (Romanian personal ID: 13 digits) in
  extracted text if `redact_pii: true` is set on the config (opt-in).
- Declarații de avere are public-law documents but contain names and
  property info — caller decides downstream whether to index them.

### 7.4 Logging
- Logs MUST NOT persist document content beyond 7 days.
- Redact API keys in all logs.

## 8. Observability

Each response SHOULD include:

```
X-Request-ID: <echo>
X-Vendor-Trace-ID: <provider>
X-Vendor-Cache-Status: HIT | MISS
Server-Timing: fetch;dur=812, render;dur=1940, extract;dur=245, classify;dur=105
```

See §13.6 for the full Prometheus + OpenTelemetry emission requirements.

## 9. Versioning & Deprecation

- Semver on the path (`/v1/*`).
- Breaking change = new major, both served ≥ 6 months.
- `Sunset: <date>` header announces removal.

## 10. Cost Model (for vendor RFI)

Please state pricing on these axes — caller will model monthly cost:

1. **Per-URL scraped** (inclusive of retries, renders): $__/URL
2. **Per-PDF downloaded**: $__/PDF
3. **JS-rendered page premium**: +$__/URL
4. **Storage of binaries** (per GB-month): $__
5. **Monthly minimum** or platform fee: $__
6. **Classification included?** Yes / No / add-on at $__/call
7. **Structured extraction (4.8)?** Yes / No / add-on at $__/call

**Caller's estimated monthly volume (initial rollout, ~20 cityhalls):**

- ~50,000 page scrapes / month
- ~5,000 PDFs / month
- ~30 % JS-rendered
- ~40,000 classifications / month

## 11. Open Questions

Please answer these before starting implementation. They drive scoping,
cost modelling, and the onboarding timeline.

1. Will you implement the full Romanian municipal taxonomy (§3.3)
   natively, or return raw content and let the caller classify?
2. Do you track incremental-crawl state server-side (caller passes
   only `previous_job_id`) or do we always supply `known_content_hashes`
   on every delta crawl?
3. How long do you retain original binaries behind `binary_url`? The
   spec floors this at 30 days — we want to confirm your commit.
4. Will you implement webhooks (§5) and structured extraction (§4.8),
   or should the caller poll + extract client-side?
5. What is your anti-bot strategy (residential proxy pool, fingerprint
   rotation, CAPTCHA solver) and who supplies / funds it?
6. What framework / stack are you building on (Scrapy, Playwright,
   headless Chromium cluster, serverless, bespoke)?
7. What is your pricing model — per URL, per PDF, per GB stored,
   monthly platform fee, or a blend? Please itemize against §10.
8. What timeline can you commit to for reaching the §6.1 performance
   SLOs and §6.3 Romanian quality gate on the caller's eval set?

---

## 12. Reserved

Intentionally left blank in v1 so subsequent majors can slot new
sections without renumbering.

---

## 13. Handoff to Caller

Delivered documents are consumed by the Lex-Advisor platform's
ingestion layer — no vendor action required beyond conforming to this
spec. The caller fetches results via `GET /v1/jobs/{id}/documents` (or
receives them via the §5 webhook when configured) and hands them to its
RAG indexing pipeline.

---

## 14. Packaging & Delivery

### 14.1 What you deliver to us

- **Source code** in a Bitbucket repo under our organization (we'll
  create and grant you developer access). Python 3.12 is our preferred
  stack; if you propose a different language, raise it up front.
- **Semver git tags** on releases (`vX.Y.Z`). Follow Conventional
  Commits (`feat:` → minor, `fix:` → patch, `BREAKING CHANGE:` → major).
  Tags on `main` trigger our CI.
- **A Dockerfile** at the repo root. Requirements:
  - Multi-stage build (builder + runtime).
  - Non-root runtime user (uid 1000, named `appuser`).
  - Pinned base image by SHA-256 digest (never `latest`).
  - Service listens on port **8080**.
  - `HEALTHCHECK` calling `GET /v1/health`.
  - Logs to stdout (structured JSON recommended).
  - Handles SIGTERM gracefully — drain in-flight requests before exit.
  - Final image size under 500 MB unless justified.
- **A `docker-compose.service.yml` fragment** showing how the service
  should be run alongside our existing stack. Exactly one service (plus
  any DB/Redis/browser/proxy it needs). No host ports exposed. Joins an
  external network named `lex-advisor`. Env-var driven (no hardcoded
  values).
- **An OpenAPI document** (`openapi.yaml`) in the repo root and
  served at `GET /v1/openapi.json` on the running service.
- **A `README.md`** with: prerequisites, `docker compose up` local run,
  env var table, smoke test commands, troubleshooting runbook
  (including how to swap the proxy pool).

### 14.2 How we build and deploy your image

You do NOT need any Google Cloud credentials. The flow is:

1. You push code + a semver tag to the Bitbucket repo we provide.
2. Our **self-hosted Bitbucket Pipelines runner** (running on our
   infrastructure) picks up the push.
3. The runner builds your Docker image from your Dockerfile, runs
   lint + tests + Trivy security scan, and — on tagged releases —
   pushes the image to our private GCP Artifact Registry.
4. We deploy the tagged image into our stack using the compose
   fragment you supplied.

So your `bitbucket-pipelines.yml` only needs to define the build + test
+ scan steps. The push target is our runner's concern, not yours.

### 14.3 CI pipeline you provide

Your `bitbucket-pipelines.yml` should include, at minimum:

- **On every pull request:**
  1. Lint (`ruff`, `mypy`, or equivalents for your language).
  2. Unit tests (aim for ≥ 80 % coverage).
  3. Integration tests against your own containerised DB/Redis.
  4. Build the Docker image.
  5. Run a CVE scan (Trivy or equivalent) — fail on any CRITICAL or
     HIGH finding.

- **On semver tag push (`v*.*.*`):**
  6. Re-run the above end to end. Our runner handles the image push
     after this completes green.

### 14.4 Database and storage

If your service needs persistence (Postgres, Redis, object storage,
browser cluster), declare it inside `docker-compose.service.yml`. You
own its schema, volume, credentials, and backups. Do NOT rely on our
shared Postgres or Redis. Do NOT share secrets outside your own
containers. Pre-signed `binary_url` buckets are yours to manage.

### 14.5 Authentication you implement

- Inbound requests to your service carry
  `Authorization: Bearer <api_key>` (§2). You validate and reject
  mismatches with `401 unauthorized`.
- Outbound webhooks you send us MUST be HMAC-SHA256-signed over the
  raw body, header `X-Vendor-Signature: sha256=<hex>`. We exchange the
  webhook shared secret out of band on provisioning.
- No mTLS required for v1. No TLS required on internal Docker-network
  traffic between our stack and your service (we handle the TLS edge
  on our public endpoints).

### 14.6 Observability you implement

Mandatory from day 1, regardless of whether we have consumers ready:

| Requirement | Details |
|---|---|
| `GET /metrics` | Prometheus exposition format. Minimum metrics: `http_requests_total{method,status,endpoint}`, `http_request_duration_seconds`, `vendor_cost_usd_total`, `vendor_tokens_total{direction}`, `vendor_external_api_errors_total{dependency,error_type}`. |
| OpenTelemetry | Use `opentelemetry-distro` (or language equivalent) with auto-instrumentation for your HTTP server, DB client, and HTTP client. Env-driven: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`. Unset endpoint → no-op (safe for local dev). |
| Trace-log correlation | Every log line includes `trace_id` + `span_id` from the current OTel span context, plus the `X-Request-ID` value from the inbound header. |
| Response headers | Echo `X-Request-ID`; emit `X-Vendor-Trace-ID`; emit `Server-Timing` header or equivalent JSON body fields. |

---

## 15. Testing the Implementation

This section tells you how to smoke-test the service you have built, what
reference Romanian data we will probe it with, how our contract-test suite
works, and what we will do before we accept delivery.

### 15.1 Quick-start smoke test

Drop-in curl commands for the hot endpoints. Replace `<api_key>` with the
Bearer token we gave you, keep `X-Tenant-ID: ph-balta-doamnei` for the canary
cityhall, and generate a fresh UUID for every `X-Request-ID` /
`Idempotency-Key`.

#### `POST /v1/scrape` (sync)

```bash
curl -sS -X POST http://localhost:8080/v1/scrape \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: 11111111-1111-4111-8111-111111111111" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Idempotency-Key: 22222222-2222-4222-8222-222222222222" \
  -d '{
    "url": "https://primariatimisoara.ro/hcl/hcl-125-2024",
    "render_javascript": "auto",
    "follow_redirects": true,
    "include_raw_html": false,
    "classify": true,
    "timeout_ms": 30000,
    "mode": "sync"
  }'
```

Expected response (200):

```json
{
  "request_id": "11111111-1111-4111-8111-111111111111",
  "document": {
    "document_id": "d_7c3e9a1f",
    "source_url": "https://primariatimisoara.ro/hcl/hcl-125-2024",
    "mime_type": "text/html",
    "content_type": "html",
    "raw_text": "Hotărârea nr. 125 din 22.04.2024 privind aprobarea bugetului local ...",
    "doc_type": "hcl",
    "doc_type_confidence": 0.94,
    "title": "HCL nr. 125/2024 privind aprobarea bugetului local",
    "language": "ro",
    "published_at": "2024-04-22",
    "content_length": 48210,
    "content_hash": "sha256:abc123...",
    "extraction_confidence": 0.88,
    "warnings": []
  },
  "latency_ms": 2341
}
```

#### `POST /v1/crawl`

```bash
curl -sS -X POST http://localhost:8080/v1/crawl \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: 33333333-3333-4333-8333-333333333333" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Idempotency-Key: 44444444-4444-4444-8444-444444444444" \
  -d '{
    "config": {
      "seed_urls": ["https://primariatimisoara.ro/"],
      "allowed_domains": ["primariatimisoara.ro"],
      "max_depth": 5,
      "max_pages": 2000,
      "include_patterns": ["/hcl/", "/dispozitii/", "/monitorul-oficial-local/"],
      "doc_types_wanted": ["hcl", "dispozitie_primar", "regulament", "buget"],
      "respect_robots_txt": true,
      "max_requests_per_second": 1.0,
      "follow_pdfs": true,
      "render_javascript": "auto"
    },
    "priority": "normal"
  }'
```

Expected response (202):

```json
{
  "job_id": "cj_9f8e7d6c",
  "status": "queued",
  "submitted_at": "2026-04-22T10:00:00Z",
  "estimated_completion_at": "2026-04-22T10:35:00Z"
}
```

#### `GET /v1/jobs/{job_id}`

```bash
curl -sS http://localhost:8080/v1/jobs/cj_9f8e7d6c \
  -H "Authorization: Bearer <api_key>" \
  -H "X-Tenant-ID: ph-balta-doamnei"
```

Expected response (200):

```json
{
  "job_id": "cj_9f8e7d6c",
  "tenant_id": "ph-balta-doamnei",
  "status": "running",
  "progress": {
    "stage": "crawling",
    "urls_discovered": 1247,
    "urls_fetched": 823,
    "documents_extracted": 411,
    "urls_pending": 424
  },
  "stats": {
    "by_doc_type": { "hcl": 184, "dispozitie_primar": 62, "regulament": 28 },
    "http_errors": { "404": 12, "timeout": 5 }
  },
  "submitted_at": "2026-04-22T10:00:00Z",
  "started_at": "2026-04-22T10:00:12Z",
  "estimated_completion_at": "2026-04-22T10:35:00Z"
}
```

#### `GET /v1/jobs/{job_id}/documents`

```bash
curl -sS "http://localhost:8080/v1/jobs/cj_9f8e7d6c/documents?limit=100&min_confidence=0.5&doc_type=hcl" \
  -H "Authorization: Bearer <api_key>" \
  -H "X-Tenant-ID: ph-balta-doamnei"
```

Expected response (200):

```json
{
  "documents": [
    {
      "document_id": "d_abc123",
      "source_url": "https://primariatimisoara.ro/hcl/hcl-125-2024",
      "mime_type": "application/pdf",
      "content_type": "pdf",
      "raw_text": "Hotărârea nr. 125 din 22.04.2024 ...",
      "doc_type": "hcl",
      "doc_type_confidence": 0.94,
      "title": "HCL nr. 125/2024",
      "language": "ro",
      "page_count": 12,
      "content_length": 48210,
      "content_hash": "sha256:abc123...",
      "extraction_confidence": 0.88,
      "warnings": []
    }
  ],
  "next_cursor": "eyJvZmZzZXQiOiAxMDB9",
  "has_more": true,
  "total_available": 184
}
```

#### `GET /v1/health`

```bash
curl -sS http://localhost:8080/v1/health
```

Expected response (200):

```json
{
  "status": "ok",
  "version": "1.2.3",
  "uptime_seconds": 123456,
  "dependencies": {
    "proxy_pool": "ok",
    "browser_cluster": "ok",
    "storage": "ok",
    "classifier": "ok"
  },
  "queue_depth": 18,
  "active_workers": 24
}
```

### 15.2 Reference test data

We probe every candidate implementation with the following Romanian cityhall
seeds. Use them as your own integration fixtures — they are the same targets
we use on our side.

**Case 1 — Bucharest (București), large site, heavy JS rendering.**

- Seed: `https://primariabucuresti.ro/`
- Allowed domains: `["primariabucuresti.ro"]`
- Expected `doc_type` distribution hint: majority `hcl` +
  `dispozitie_primar`, sizeable `anunt_public` and `consultare_publica`,
  small amount of `regulament` and `buget`. We expect ≥ 500 distinct HCLs
  discoverable.
- Provider must preserve diacritics (`ă ș ț î â`) in `raw_text` — we
  regression-check against strings like "Hotărârea privind bugetul".
- `render_javascript: "auto"` — site uses a JS-heavy CMS; provider must
  detect and render.

**Case 2 — Sibiu, mid-size site, mostly static HTML + PDFs.**

- Seed: `https://www.sibiu.ro/`
- Allowed domains: `["www.sibiu.ro"]`
- Expected `doc_type` distribution hint: mix of `hcl`, `dispozitie_primar`,
  `regulament`, `pug` / `puz` (urbanism-heavy), and `proiect_hotarare` on
  the pre-vote page. PDFs dominate for HCLs.
- We check incremental correctness — running the same crawl with
  `incremental.known_content_hashes` set to the first crawl's result MUST
  return zero documents if the site hasn't changed.

**Case 3 — Timișoara, sitemap-driven site.**

- Seed: `https://primariatimisoara.ro/`
- Allowed domains: `["primariatimisoara.ro"]`
- `sitemap_hint_url: "https://primariatimisoara.ro/sitemap.xml"`
- Expected `doc_type` distribution hint: majority `hcl` from
  `/monitorul-oficial-local/`, plus `act_normativ_local`, `regulament`,
  `buget`, `raport_executie_bugetara`. Provider should follow the sitemap
  instead of brute-force link walking — we compare URL discovery recall
  with and without the hint.
- Diacritic check: city name written `Timișoara` (with `ș` comma-below,
  not `ş` cedilla) MUST round-trip unchanged through `raw_text`.

### 15.3 Contract tests

**Contract tests:** we will provide a Schemathesis-based test harness + a
set of Romanian-language domain tests as part of the onboarding package.
They run via `pytest` against your local/staging deployment. The suite
exercises the full OpenAPI surface plus hand-written tests for
Romanian-specific behaviour (see §6 quality gates). Your implementation
must pass the suite before we accept delivery.

The suite combines:

1. **Schemathesis property-based tests** derived from the committed OpenAPI
   YAML (`docs/external/scraper-api-spec.yaml`) — fuzzes every endpoint,
   checks status codes, required fields, idempotency, header echo,
   pagination cursor round-trips.
2. **Hand-written domain-semantic tests** — coverage of the 18-class
   `doc_type` taxonomy (§3.3), incremental-crawl correctness (known hashes
   yield zero duplicates), Romanian diacritic preservation in `raw_text`,
   SSRF defence on seed URLs, robots.txt compliance, cross-tenant isolation,
   and `binary_url` TTL honoured.

Failed test IDs + a reproduction fixture ship with every release so you can
rerun locally.

### 15.4 Our acceptance process

Before cutover, we run the contract test suite plus an independent eval set
(20 curated Romanian cityhall crawl targets, spanning small rural primării to
large municipii, with hand-labelled expected URL and `doc_type` distributions)
against your deployed service. Quality gates are defined in §6.3 of this spec
— we will not cut over unless every numeric target is met (≥ 90 % URL
recall, ≥ 85 % extraction precision, ≥ 80 % classification accuracy, ≥ 95 %
diacritic preservation). We also run a period of manual exploratory testing
on a canary cityhall (both the new service and the existing pipeline invoked
per crawl, results diffed offline, never fed into production indices) before
flipping traffic.

---

## 16. Deliverable Bundle & Handoff

On "delivery day" we expect a single handoff email linking to everything
below. Anything missing is a blocker — we will not accept delivery until the
bundle is complete. Think of this as our Definition of Done.

- [ ] **Bitbucket repo URL** at `bitbucket.org/<our-org>/lex-advisor-scraper`
      (or agreed variant) with read + push access granted to our team
      accounts.
- [ ] **Semver git tag (`vX.Y.Z`)** pushed to the Bitbucket repo; our
      self-hosted runner handles the image build + push after your tagged
      pipeline passes. Confirm the tag pipeline completed green.
- [ ] **`openapi.yaml`** committed at repo root and exposed live at
      `GET /v1/openapi.json` on the running service — byte-identical to the
      committed file.
- [ ] **`README.md`** with install, deploy, env-var reference, and an ops
      runbook (common failure modes, how to drain traffic, how to roll back,
      how to rotate API keys, how to swap the proxy pool).
- [ ] **CI logs** showing the full contract-test suite GREEN on the release
      tag commit.
- [ ] **Eval run results** meeting every §6.3 quality gate (≥ 90 % URL
      recall, ≥ 85 % extraction precision, ≥ 80 % `doc_type` classification
      accuracy, ≥ 95 % diacritic preservation, p95 latency within spec) on
      our 20-cityhall eval set — raw JSON + PDF summary.
- [ ] **Security scan report** (Trivy or equivalent) on the release image,
      clean on CRITICAL + HIGH.
- [ ] **`LICENSE`** file in the repo (Apache-2.0 WITH Commons-Clause-1.0 default, or pre-approved
      alternative).
- [ ] **Signed IP assignment clause** (for any custom work) + signed DPA +
      EU data residency attestation (`europe-west3` or other approved EU
      region).
- [ ] **30-day post-delivery support SOW** covering bug fixes, SLO breaches,
      target-site blocking incidents, and at least one named engineer.
- [ ] **Status page URL** + named 24/7 on-call contact (phone + email +
      escalation chain).

Fail any of the above and we do not accept delivery until fixed — no hard
cutover.

---

## 17. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-04-22 | Initial public spec for external implementers. |
