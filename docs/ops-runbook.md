# Operations Runbook

## Service Management

### Start/Stop

```bash
# Start all services
docker compose up -d

# Stop (preserve data volumes)
docker compose down

# Stop and destroy all data
docker compose down -v

# Rebuild and restart
docker compose up -d --build
```

### Monitoring

```bash
# Service status
docker compose ps

# Follow all logs
docker compose logs -f

# Follow API logs only
docker compose logs -f scraper-api

# Health check
curl http://localhost:8080/v1/health
```

### Scaling

```bash
# Scale API workers (if using replicas)
docker compose up -d --scale scraper-api=3
```

---

## Traffic Management

### Drain Traffic
Scale `scraper-api` to 0 or stop the container. RabbitMQ will hold queued messages until workers come back.

### Rolling Restart
```bash
docker compose restart scraper-api
```

### Rollback
```bash
docker compose up -d --image lex-advisor/scraper-api:<previous-tag>
```

---

## Database Operations

### Run Migrations
```bash
docker compose exec scraper-api alembic upgrade head
```

### Check Migration Status
```bash
docker compose exec scraper-api alembic current
```

### Create New Migration
```bash
docker compose exec scraper-api alembic revision --autogenerate -m "description"
```

### Connect to PostgreSQL
```bash
docker compose exec postgres psql -U lex -d scraper
```

GUI tools (DBeaver, pgAdmin4) connect to `localhost:5432`, database `scraper`, user `lex`, password `lex`.

---

## Redis Operations

### Flush All Data
```bash
docker compose exec redis redis-cli FLUSHALL
```

### Inspect Keys
```bash
# Count idempotency keys
docker compose exec redis redis-cli KEYS "IDEM:*" | wc -l

# Check job progress
docker compose exec redis redis-cli HGETALL "JOB:progress:<job_id>"

# Check rate limit bucket
docker compose exec redis redis-cli HGETALL "DOMAIN:rate:<domain>"
```

GUI: RedisInsight connects to `localhost:6379`.

---

## RabbitMQ Operations

### Management UI
Open `http://localhost:15672` (credentials: `guest`/`guest`).

### Purge DLQ
```bash
docker compose exec rabbitmq rabbitmqadmin purge queue name=webhooks.dlq
```

### Check Queue Depth
```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

---

## Security Operations

### Rotate API Key
1. Update `API_KEY` in `.env`
2. `docker compose restart scraper-api`
3. Update all clients with new key

### Rotate Webhook Secret
1. Update `WEBHOOK_SECRET` in `.env`
2. `docker compose restart scraper-api`
3. Update receiver to verify new HMAC key

---

## Common Failure Modes

| Symptom | Cause | Fix |
|---|---|---|
| `429 Rate Limited` | Hitting target sites too fast | Lower `max_requests_per_second` in crawl config |
| `502 Upstream Error` | Target site down or blocking | Check proxy config, try different user agent |
| `422 SSRF` | Seed URL resolves to private IP | Use public URLs only |
| Worker queue growing | Workers can't keep up | Scale workers or reduce `max_pages` |
| Health returns `degraded` | Redis or Postgres unreachable | Check container logs, network |
| `409 Duplicate Job` | Same idempotency key, different body | Generate a new `Idempotency-Key` UUID |

---

## Maintenance

### Log Level Change (without restart)
Currently requires restart. Set `LOG_LEVEL` env var and restart:
```bash
LOG_LEVEL=DEBUG docker compose restart scraper-api
```

### Cleanup Expired Jobs
Expired jobs are tracked via `JOB:expired:<id>` Redis keys. The data remains in PostgreSQL until explicitly deleted.

### Image Size Check
```bash
docker images lex-advisor/scraper-api --format "{{.Size}}"
```
Target: < 500 MB.
