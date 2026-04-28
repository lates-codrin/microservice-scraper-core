# API Examples

Complete worked examples for every endpoint. Replace `YOUR_API_KEY` with your actual key.

## Common Headers

All authenticated endpoints require:

```
Authorization: Bearer YOUR_API_KEY
X-Request-ID: <UUID v4>
X-Tenant-ID: <tenant-slug>
```

---

## POST /v1/scrape — Single URL Scrape

### Sync Mode

```bash
curl -X POST http://localhost:8080/v1/scrape \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://primaria-bucuresti.ro/hotarari/hcl-123-2024",
    "render_javascript": "auto",
    "follow_redirects": true,
    "include_raw_html": false,
    "classify": true,
    "extract_structured": true,
    "timeout_ms": 30000,
    "mode": "sync"
  }'
```

**Response** (200):
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "document": {
    "document_id": "d_a1b2c3d4e5f6",
    "source_url": "https://primaria-bucuresti.ro/hotarari/hcl-123-2024",
    "canonical_url": "https://primaria-bucuresti.ro/hotarari/hcl-123-2024",
    "mime_type": "text/html",
    "content_type": "html",
    "raw_text": "Hotărârea nr. 123/2024 privind aprobarea bugetului local...",
    "doc_type": "hcl",
    "doc_type_confidence": 0.94,
    "title": "HCL 123/2024",
    "language": "ro",
    "content_length": 4523,
    "content_hash": "sha256:abc123...",
    "metadata": {
      "discovered_at": "2024-04-27T12:00:00Z",
      "http_status": 200,
      "structured_fields": {
        "hcl_number": "123/2024",
        "adoption_date": "2024-03-15",
        "subject": "aprobarea bugetului local"
      }
    },
    "extraction_confidence": 0.94,
    "warnings": []
  },
  "latency_ms": 1250
}
```

### Async Mode

```bash
curl -X POST http://localhost:8080/v1/scrape \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://primaria-sibiu.ro/document.pdf", "mode": "async"}'
```

**Response** (202):
```json
{
  "job_id": "sj_abc123def456",
  "status": "queued"
}
```

---

## POST /v1/crawl — Multi-URL Crawl

```bash
curl -X POST http://localhost:8080/v1/crawl \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "seed_urls": [
        "https://primaria-bucuresti.ro/hotarari",
        "https://primaria-sibiu.ro/acte"
      ],
      "allowed_domains": ["primaria-bucuresti.ro", "primaria-sibiu.ro"],
      "max_depth": 3,
      "max_pages": 500,
      "doc_types_wanted": ["hcl", "dispozitie_primar"],
      "respect_robots_txt": true,
      "max_requests_per_second": 2.0,
      "render_javascript": "auto"
    },
    "callback_url": "https://your-app.example/webhooks/scraper",
    "priority": "normal"
  }'
```

**Response** (202):
```json
{
  "job_id": "cj_abc123def456",
  "status": "queued",
  "submitted_at": "2024-04-27T12:00:00Z",
  "estimated_completion_at": "2024-04-27T12:30:00Z"
}
```

---

## GET /v1/jobs/{job_id} — Poll Job Status

```bash
curl http://localhost:8080/v1/jobs/cj_abc123def456 \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei"
```

**Response** (200, with `Retry-After: 30` if still crawling):
```json
{
  "job_id": "cj_abc123def456",
  "tenant_id": "ph-balta-doamnei",
  "status": "crawling",
  "progress": {
    "stage": "crawling",
    "urls_discovered": 150,
    "urls_fetched": 87,
    "documents_extracted": 85,
    "documents_classified": 80,
    "urls_pending": 63,
    "bytes_downloaded": 12456789
  },
  "stats": {
    "by_doc_type": {"hcl": 45, "dispozitie_primar": 12, "other": 23},
    "http_errors": {"404": 2}
  },
  "submitted_at": "2024-04-27T12:00:00Z",
  "started_at": "2024-04-27T12:00:05Z",
  "estimated_completion_at": "2024-04-27T12:30:00Z"
}
```

---

## GET /v1/jobs/{job_id}/documents — Paginated Results

```bash
# First page
curl "http://localhost:8080/v1/jobs/cj_abc123def456/documents?limit=50&doc_type=hcl&min_confidence=0.8" \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei"

# Next page (using cursor from previous response)
curl "http://localhost:8080/v1/jobs/cj_abc123def456/documents?limit=50&cursor=NTA=" \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei"
```

---

## POST /v1/jobs/{job_id}/cancel

```bash
curl -X POST http://localhost:8080/v1/jobs/cj_abc123def456/cancel \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei"
```

**Response** (200):
```json
{
  "job_id": "cj_abc123def456",
  "status": "cancelled",
  "documents_salvaged": 85
}
```

---

## DELETE /v1/jobs/{job_id}

```bash
curl -X DELETE http://localhost:8080/v1/jobs/cj_abc123def456 \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei"
```

**Response**: 204 No Content

---

## POST /v1/classify

```bash
curl -X POST http://localhost:8080/v1/classify \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hotărârea nr. 123/2024 a Consiliului Local privind aprobarea bugetului local",
    "url_hint": "https://primaria-bucuresti.ro/hotarari/hcl-123",
    "title_hint": "HCL 123/2024"
  }'
```

**Response** (200):
```json
{
  "doc_type": "hcl",
  "doc_type_confidence": 0.94,
  "language": "ro",
  "alternatives": [
    {"doc_type": "buget", "confidence": 0.3}
  ]
}
```

---

## POST /v1/extract

```bash
curl -X POST http://localhost:8080/v1/extract \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -H "X-Request-ID: $(uuidgen)" \
  -H "X-Tenant-ID: ph-balta-doamnei" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hotărârea nr. 42/2024 din 15.03.2024 privind aprobarea organigramei. Voturi: pentru: 21 împotrivă: 2 abțineri: 1",
    "doc_type": "hcl",
    "schema": {"fields": ["hcl_number", "adoption_date", "subject", "votes"]}
  }'
```

**Response** (200):
```json
{
  "fields": {
    "hcl_number": "42/2024",
    "adoption_date": "2024-03-15",
    "subject": "aprobarea organigramei",
    "votes": {"for": 21, "against": 2, "abstain": 1}
  },
  "field_confidence": {
    "hcl_number": 0.99,
    "adoption_date": 0.90,
    "subject": 0.85,
    "votes": 0.95
  },
  "missing_fields": []
}
```

---

## GET /v1/health

```bash
curl http://localhost:8080/v1/health
```

**Response** (200):
```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "dependencies": {
    "redis": "ok",
    "postgres": "ok",
    "browser_cluster": "ok",
    "classifier": "ok"
  },
  "queue_depth": 3,
  "active_workers": 4
}
```

---

## Error Responses

All errors follow the standard envelope:

```json
{
  "error": {
    "code": "not_found",
    "message": "Job 'cj_nonexistent' was not found.",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "details": {}
  }
}
```

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | Missing/invalid required headers |
| 401 | `unauthorized` | Bad or missing Bearer token |
| 403 | `forbidden` | Tenant mismatch |
| 404 | `not_found` | Job/resource not found |
| 409 | `duplicate_job` | Idempotency key reused with different body |
| 410 | `gone` | Job results expired |
| 422 | `validation_error` | Request body validation failed |
| 429 | `rate_limited` | Rate limit exceeded |
| 501 | `not_implemented` | Unsupported extraction type |
| 502 | `upstream_error` | Target site unreachable |
