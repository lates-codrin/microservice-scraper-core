# Lex-Advisor Scraper Service

High-performance, reliable scraper for Romanian municipal documents.

## Features

- **Async Crawling**: BFS frontier with RabbitMQ.
- **JS Rendering**: Playwright-based rendering with auto-detection.
- **Robust Extraction**: HTML (trafilatura) and PDF (pdfplumber) processing.
- **Classification**: Rule-based taxonomy for Romanian municipal docs.
- **Incremental Crawl**: Skip unchanged documents using content hashes.
- **Hardened**: Non-root Docker, multi-stage builds, SSRF protection.

## Infrastructure Setup

This service requires three main infrastructure components:
1. **PostgreSQL**: For persistent storage of jobs and documents.
2. **Redis**: For rate-limiting, idempotency-key storage, and temporary state.
3. **RabbitMQ**: For asynchronous crawling and webhook delivery.

### Option 1: Docker Desktop (Recommended)
If you have **Docker Desktop** installed on Windows, you don't need to manually install or configure any of these services. The included `docker-compose.yml` handles everything.

1. **Start Services**: 
   ```bash
   docker compose up -d
   ```
   This will spin up:
   - `postgres` (on port 5432)
   - `redis` (on port 6379)
   - `rabbitmq` (on port 5672, management UI on 15672)
   - `scraper-api` (on port 8080)

2. **Database Initialization**:
   Migrations are managed via Alembic. When running via Docker, the tables are initialized automatically if the volume is new. To run migrations manually:
   ```bash
   docker compose exec scraper-api alembic upgrade head
   ```

### Option 2: Manual / External Services
If you prefer to use external services, update the connection strings in your `.env` file:

- **Postgres**: `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname`
- **Redis**: `REDIS_URL=redis://host:6379/0`
- **RabbitMQ**: `RABBITMQ_URL=amqp://user:pass@host:5672/`

## Installation

### Prerequisites

- Docker Desktop (for Windows users)
- Python 3.12 (optional, for local linting/scripts)

### Quick Start

1. Clone the repo.
2. `cp .env.example .env`
3. Open Docker Desktop.
4. Run `docker compose up --build`

The service will be available at `http://localhost:8080`.
You can access the RabbitMQ Management UI at `http://localhost:15672` (guest/guest).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | Bearer token for authentication | `dev-api-key-change-me` |
| `DEFAULT_TENANT_ID` | Default tenant slug | `ph-balta-doamnei` |
| `RABBITMQ_URL` | RabbitMQ connection string | `amqp://guest:guest@rabbitmq:5672/` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://lex:lex@postgres:5432/scraper` |
| `REDIS_URL` | Redis string | `redis://redis:6379/0` |

## Ops Runbook

### Traffic Management
- **Drain Traffic**: Scale `scraper-api` to 0 or stop the container. RabbitMQ will hold the queue.
- **Rollback**: `docker compose up -d --image lex-advisor/scraper-api:<prev-tag>`.

### Security
- **Rotate API Keys**: Update `API_KEY` in `.env` and restart the service.
- **Swap Proxy Pool**: Update proxy environment variables (if implemented) and restart.

### Maintenance
- **Flush Redis**: `docker compose exec redis redis-cli flushall`.
- **Purge RabbitMQ DLQ**: `docker compose exec rabbitmq rabbitmqadmin purge queue=webhooks_dlq`.
- **Clean Database**: Use Alembic migrations to manage schema.

### Common Failure Modes
- **429 Rate Limited**: Scraper is hitting target sites too fast. Adjust `max_requests_per_second`.
- **502 Upstream Error**: Target site is down or blocking. Check proxies.
- **Worker Lag**: RabbitMQ queue is growing. Scale `scraper-api` or check worker logs.

## Testing

Run the full test suite:
```bash
docker compose run test
```

Or locally:
```bash
pytest tests
```
