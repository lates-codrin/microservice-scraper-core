# Security Policy

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

We will coordinate disclosure timing with you and credit you in the release notes.

---

## Threat Model Summary

### Assets protected

| Asset | Protection |
|---|---|
| Scraped document content | Tenant-isolated DB queries; `tenant_id` enforced on every read/write |
| API credentials | Bearer token validated per-request; rotated via environment secret |
| Webhook HMAC secret | Never logged; only used inside `run_webhook_worker` |
| Redis job state | Atomic `SET NX` prevents duplicate jobs; no raw eval |
| PDF / HTML fetch targets | SSRF defence (DNS + IP blocklist) on every outbound hop |

### SSRF Defence

All outbound HTTP requests use a manual redirect loop in `app/services/fetcher.py` that resolves each redirect target to an IP address and rejects:

- RFC-1918 private ranges (10/8, 172.16/12, 192.168/16)
- Loopback (127.0.0.0/8)
- Link-local (169.254/16)
- IPv6 private / loopback / link-local

Webhook delivery in `app/services/webhooks.py` enforces the same blocklist with `follow_redirects=False` on the outbound `httpx` call.

Incoming seed URLs validated in `app/models/crawl.py` (`CrawlConfig.validate_ssrf`) via socket DNS resolution before the job is queued.

### Injection Hardening

- Slug / header values in `app/middleware/auth_headers.py` are validated with `_SAFE_SLUG_RE = re.compile(r'^[\x20-\x7E]+$')`, rejecting any control characters.
- All DB queries use SQLAlchemy parameterised statements; no raw string interpolation.
- `CrawlAuth.type` constrained to `Literal["basic", "cookie", "form"]` — no arbitrary strings forwarded to upstream auth handlers.
- Boolean request fields use `StrictBool`; string fields use `StrictStr` where appropriate to prevent Pydantic type-coercion surprises.

### Tenant Isolation

Every `JobStore` method appends a `WHERE tenant_id = :tenant_id` clause.  
The `tenant_id` is extracted from the validated `X-Tenant-ID` header by `app/middleware/auth_headers.py` and stored on `request.state`; it is never taken from the request body.

### Idempotency

POST `/v1/crawl` and POST `/v1/scrape` both require a UUID `Idempotency-Key` header. The crawl endpoint stores the key in Redis with `SET NX EX 86400`; duplicate keys within 24 h return the existing job rather than creating a new one, preventing double-charging or state pollution.

---

## CVE Audit (last run: 2026-04-27)

All findings were remediated in `requirements.txt`:

| CVE | Package | Fixed version |
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
| Header injection | `tests/test_security.py` | Control-char rejection in slug |
| Tenant isolation | `tests/test_jobs.py` | Cross-tenant read returns 404 |
| Idempotency (atomic) | `tests/test_crawl.py` | Duplicate key race returns 409 |
| Contract (Schemathesis) | `tests/contract/test_schemathesis.py` | 16 OpenAPI operations, 20 examples each |
| Load baseline | `tests/load/locustfile.py` | Locust; targets p95 < 200 ms (job poll) |
