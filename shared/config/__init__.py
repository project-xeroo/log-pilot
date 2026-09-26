"""Shared configuration base for all LogPilot services."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings shared across services."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_", extra="ignore")

    url: str = "postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    echo: bool = False


class RedisSettings(BaseSettings):
    """Redis / Celery broker settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str = "redis://localhost:6379/0"


class StorageSettings(BaseSettings):
    """Cloud object storage settings (S3-compatible)."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_", extra="ignore")

    bucket: str = "logpilot-uploads"
    endpoint_url: str = ""          # blank = use AWS default; set for MinIO / GCS
    access_key_id: str = ""
    secret_access_key: str = ""
    region: str = "us-east-1"
    presigned_url_expiry: int = 3600
