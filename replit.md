# Lex-Advisor Scraper Service

High-performance, reliable scraper for Romanian municipal documents.

## Architecture

FastAPI backend service with:
- **PostgreSQL** (Replit built-in) for persistent job/document storage
- **Redis** (fakeredis in dev, real Redis via REDIS_URL env var) for rate-limiting and idempotency
- **RabbitMQ** (optional, for async crawling — not required to start)
- **Alembic** for database migrations

## Key Components

- `app/main.py` — FastAPI app factory with middleware setup
- `app/settings.py` — Configuration from environment variables
- `app/db.py` — SQLAlchemy async engine setup
- `app/dependencies.py` — FastAPI dependency injection (JobStore)
- `app/routers/` — API route handlers (scrape, crawl, jobs, classify, extract, health)
- `app/services/` — Business logic (job_store, fetcher, extractor, classifier, frontier)
- `app/models/` — Pydantic + SQLAlchemy models
- `app/middleware/` — Auth headers and rate limiting
- `alembic/` — Database migration scripts

## Running

The app runs on port 5000 via:
```
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (auto-set by Replit) | — |
| `API_KEY` | Bearer token for auth | `dev-api-key-change-me` |
| `DEFAULT_TENANT_ID` | Default tenant slug | `ph-balta-doamnei` |
| `REDIS_URL` | Redis URL (optional, uses fakeredis if absent) | — |
| `RABBITMQ_URL` | RabbitMQ URL (optional) | `amqp://guest:guest@localhost:5672/` |
| `SERVICE_VERSION` | Service version string | `1.0.0` |
| `ACTIVE_WORKERS` | Worker count | `4` |

## API Usage

All requests require:
- `Authorization: Bearer <API_KEY>`
- `X-Request-ID: <UUID>`
- `X-Tenant-ID: <tenant_slug>`

Example health check:
```bash
curl -H "Authorization: Bearer dev-api-key-change-me" \
     -H "X-Request-ID: 550e8400-e29b-41d4-a716-446655440000" \
     -H "X-Tenant-ID: ph-balta-doamnei" \
     http://localhost:5000/v1/health
```

## Database Migrations

Run migrations with:
```bash
alembic upgrade head
```

## Replit-Specific Adaptations

1. `DATABASE_URL` is automatically converted from `postgresql://` to `postgresql+asyncpg://` in `settings.py`
2. Redis falls back to fakeredis when `REDIS_URL` is not set or unreachable
3. App runs on `0.0.0.0:5000` for Replit preview compatibility
