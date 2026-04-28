# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Application settings loaded from environment variables (twelve-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration populated from env vars."""

    api_key: str
    default_tenant_id: str
    service_version: str
    active_workers: int
    rabbitmq_url: str
    database_url: str
    redis_url: str
    docs_enabled: bool
    log_level: str
    browser_workers: int
    webhook_secret: str


def _env_int(name: str, default_value: int) -> int:
    """Parse an integer env var with a fallback default."""
    value = os.getenv(name, str(default_value))
    try:
        return int(value)
    except ValueError:
        return default_value


def _env_bool(name: str, default_value: bool) -> bool:
    """Parse a boolean env var (accepts true/1/yes)."""
    value = os.getenv(name, str(default_value)).lower()
    return value in ("true", "1", "yes")


def _normalize_database_url(url: str) -> str:
    """Convert postgresql:// to postgresql+asyncpg:// for async driver."""
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    # Strip sslmode from query string as asyncpg handles it differently
    if "?sslmode=" in url:
        url = url.split("?sslmode=")[0]
    return url


def load_settings() -> Settings:
    """Build settings from environment variables."""
    database_url = _normalize_database_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://lex:lex@localhost:5432/scraper",
        )
    )
    return Settings(
        api_key=os.getenv("API_KEY", "dev-api-key-change-me"),
        default_tenant_id=os.getenv("DEFAULT_TENANT_ID", "ph-balta-doamnei"),
        service_version=os.getenv("SERVICE_VERSION", "1.0.0"),
        active_workers=_env_int("ACTIVE_WORKERS", 4),
        rabbitmq_url=os.getenv(
            "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        ),
        database_url=database_url,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        docs_enabled=_env_bool("DOCS_ENABLED", True),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        browser_workers=_env_int("BROWSER_WORKERS", 4),
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
    )


settings = load_settings()

__all__ = ["Settings", "load_settings", "settings"]

