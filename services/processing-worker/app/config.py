"""Processing Worker configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "processing-worker"

    # Database — sync URL for Celery tasks (psycopg2)
    database_url_sync: str = "postgresql://logpilot:logpilot@localhost:5432/logpilot"
    # Async URL for async helpers
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Object storage (S3-compatible)
    storage_bucket: str = "logpilot-uploads"
    storage_endpoint_url: str = ""
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    storage_region: str = "us-east-1"


settings = Settings()
