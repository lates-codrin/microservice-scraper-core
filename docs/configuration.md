# Configuration Reference

All configuration is via environment variables (twelve-factor methodology).

## Required Variables

| Variable | Description | Default | Example |
|---|---|---|---|
| `API_KEY` | Bearer token for API authentication | `dev-api-key-change-me` | `sk-prod-abc123...` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://lex:lex@localhost:5432/scraper` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` | `redis://:password@host:6379/0` |
| `RABBITMQ_URL` | RabbitMQ AMQP connection string | `amqp://guest:guest@localhost:5672/` | `amqp://user:pass@host:5672/vhost` |

## Optional Variables

| Variable | Description | Default | Valid Values |
|---|---|---|---|
| `DEFAULT_TENANT_ID` | Fallback tenant slug | `ph-balta-doamnei` | Any printable ASCII string |
| `SERVICE_VERSION` | Reported in health endpoint | `1.0.0` | Semver string |
| `ACTIVE_WORKERS` | Number of worker processes | `4` | 1–32 |
| `BROWSER_WORKERS` | Concurrent Playwright contexts | `4` | 1–16 |
| `LOG_LEVEL` | Minimum log level | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DOCS_ENABLED` | Enable `/docs` and `/redoc` | `true` | `true`, `false` |
| `WEBHOOK_SECRET` | HMAC key for webhook signatures | _(empty)_ | Any string |

## Database URL Normalization

The application automatically normalises database URLs:
- `postgresql://` → `postgresql+asyncpg://`
- `postgres://` → `postgresql+asyncpg://`
- `?sslmode=` query params are stripped (asyncpg handles SSL differently)

## Docker Compose Overrides

All variables can be set in `.env` (create from `.env.example`):

```bash
cp .env.example .env
# Edit .env with production values
docker compose up -d
```

Variables in `docker-compose.yml` use `${VAR:-default}` syntax, so `.env` values take precedence.

## Redis Key Namespaces

| Prefix | Purpose | TTL |
|---|---|---|
| `IDEM:{tenant}:{key}` | Idempotency guard | 24h |
| `IDEM:fp:{tenant}:{key}` | Request fingerprint | 24h |
| `JOB:known_hashes:{id}` | Incremental dedup set | Permanent |
| `JOB:retention:{id}` | Document retention flag | 30d |
| `JOB:expired:{id}` | Expired job marker | Permanent |
| `JOB:pages:{id}` | Page counter (atomic INCR) | Permanent |
| `JOB:visited:{id}` | Visited URL set | Permanent |
| `JOB:progress:{id}` | Progress hash | Permanent |
| `DOMAIN:rate:{domain}` | Token bucket state | 60s |
| `DOMAIN:robots:{domain}` | robots.txt cache | 1h |
