"""Log Ingestion Service configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    service_name: str = "log-ingestion-service"
    debug: bool = False

    # Database (PostgreSQL async)
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Celery / Redis
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Object storage (S3-compatible)
    storage_bucket: str = "logpilot-uploads"
    storage_endpoint_url: str = ""
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    storage_region: str = "us-east-1"

    # Upload limits
    max_upload_size_bytes: int = 500 * 1024 * 1024  # 500 MB
    allowed_extensions: list[str] = [".log", ".txt", ".json", ".csv", ".zip", ".gz"]

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600


settings = Settings()
