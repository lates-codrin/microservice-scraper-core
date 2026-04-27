# Stage 1: Builder
# python:3.12-slim-bookworm as of 2024-04-22
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright \
    PORT=8080

WORKDIR /app

# Install runtime dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libnss3 \
        libnspr4 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        # For OCR fallback
        tesseract-ocr \
        tesseract-ocr-ron \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --gid 1000 appuser \
    && adduser --disabled-password --gecos "" --uid 1000 --gid 1000 appuser \
    && mkdir -p /app/.playwright && chown appuser:appuser /app/.playwright

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Install Playwright browsers as root (requires system dependencies)
RUN playwright install --with-deps chromium

USER appuser

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scraper-api-spec.yaml ./scraper-api-spec.yaml
COPY .env.example ./.env.example

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/v1/health \
    -H "Authorization: Bearer ${API_KEY:-dev-api-key-change-me}" \
    -H "X-Request-ID: 00000000-0000-4000-8000-000000000001" \
    -H "X-Tenant-ID: ${DEFAULT_TENANT_ID:-ph-balta-doamnei}" || exit 1

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]