from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    default_tenant_id: str
    service_version: str
    active_workers: int
    rabbitmq_url: str
    database_url: str


def _env_int(name: str, default_value: int) -> int:
    value = os.getenv(name, str(default_value))
    try:
        return int(value)
    except ValueError:
        return default_value


def load_settings() -> Settings:
    return Settings(
        api_key=os.getenv("API_KEY", "dev-api-key-change-me"),
        default_tenant_id=os.getenv("DEFAULT_TENANT_ID", "ph-balta-doamnei"),
        service_version=os.getenv("SERVICE_VERSION", "1.0.0"),
        active_workers=_env_int("ACTIVE_WORKERS", 4),
        rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
        database_url=os.getenv("DATABASE_URL", "postgresql+asyncpg://lex:lex@localhost:5432/scraper"),
    )


settings = load_settings()