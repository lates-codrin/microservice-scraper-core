# Security Policy & Threat Model

## Supported Versions

Only the latest release of the Lex-Advisor Scraper Service receives security fixes.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.
Send a detailed report to **security@lex-advisor.example** and expect an initial response within 2 business days.

Include:
- Description of the vulnerability and affected component
- Steps to reproduce (minimal proof-of-concept preferred)
- Potential impact assessment
- Your contact details for follow-up

---

## Threat Model

### Assets Protected

| Asset | Protection Mechanism |
|---|---|
| Scraped document content | Tenant-isolated DB queries; `tenant_id` enforced on every read/write |
| API credentials | Bearer token validated per-request; rotated via environment secret |
| Webhook HMAC secret | Never logged; only used inside `run_webhook_worker` |
| Redis job state | Atomic `SET NX` prevents duplicate jobs; validated slugs prevent key injection |
| PDF / HTML fetch targets | SSRF defence (DNS + IP blocklist) on every outbound hop |

### SSRF Defence

**Three layers of protection:**

1. **Seed URL validation** (`app/models/crawl.py`): DNS resolution + IP blocklist before job is queued
2. **Fetcher redirect-chain checking** (`app/services/fetcher.py`): Manual redirect loop with SSRF check on **every hop**, preventing redirect-chain attacks landing on RFC-1918/loopback addresses
3. **Webhook delivery** (`app/services/webhooks.py`): `follow_redirects=False` + IP blocklist on callback URLs

**Blocked address ranges:**
- RFC-1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Loopback: `127.0.0.0/8`
- Link-local: `169.254.0.0/16`
- IPv6 private/loopback/link-local: `::1/128`, `fc00::/7`, `fe80::/10`

### Injection Hardening

| Vector | Protection |
|---|---|
| Header injection | `_SAFE_SLUG_RE = re.compile(r'^[\x21-\x7E]+$')` rejects control characters (NUL, CR, LF) in `X-Request-ID` and `X-Tenant-ID` |
| SQL injection | All DB queries use SQLAlchemy parameterised statements; zero raw string interpolation |
| Redis key injection | Tenant slugs validated against `_SAFE_SLUG_RE` before use in Redis key construction |
| Auth type injection | `CrawlAuth.type` constrained to `Literal["basic", "cookie", "form"]` |
| Type coercion | Boolean fields use `StrictBool`; string fields use `StrictStr` where appropriate |

### Tenant Isolation

- `tenant_id` extracted from validated `X-Tenant-ID` header (never from request body)
- `JobStore.get()` accepts optional `tenant_id` filter parameter
- All router endpoints verify `job.tenant_id == request.state.tenant_id` before returning data
- Cross-tenant access returns 403 Forbidden

### Idempotency Protection

- `POST /v1/crawl` and `POST /v1/scrape` require UUID `Idempotency-Key` header
- Redis `SET NX EX 86400` provides atomic exactly-once job creation
- Duplicate key + different request body → `409 Conflict`
- Duplicate key + same request body → returns existing job (safe retry)

### Webhook Security

- Signatures use `X-Vendor-Signature: sha256=<hmac>` (HMAC-SHA256)
- `follow_redirects=False` prevents SSRF via redirect on outbound delivery
- Callback URLs checked against the same IP blocklist as the fetcher
- 3-attempt exponential backoff (5s, 25s, 125s) before dead-letter queue

---

## CVE Audit (last run: 2026-04-27)

All findings remediated in `requirements.txt`:

| CVE | Package | Fixed Version |
|---|---|---|
| CVE-2025-71176 | pytest | ≥ 9.0.3 |
| CVE-2026-41066 | lxml | ≥ 6.1.0 |
| CVE-2026-25990 | Pillow | ≥ 12.2.0 |
| CVE-2026-40192 | Pillow | ≥ 12.2.0 |

Re-run `pip-audit` after any dependency update.

---

## Test Coverage

| Category | Location | Notes |
|---|---|---|
| SSRF (fetcher) | `tests/test_security.py` | Redirect-chain bypass, private-IP abort |
| SSRF (webhook) | `tests/test_webhooks.py` | SSRF guard on outbound delivery |
| Header injection | `tests/test_security.py` | Control-char rejection in slugs |
| Tenant isolation | `tests/test_jobs.py` | Cross-tenant read returns 403 |
| Idempotency | `tests/test_crawl.py` | Duplicate key race returns 409 |
| Contract (Schemathesis) | `tests/contract/test_schemathesis.py` | 16 OpenAPI operations, 20 examples each |
