"""API Gateway configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600

    # Downstream service URLs (for request forwarding)
    ingestion_service_url: str = "http://log-ingestion-service:8001"
    ai_service_url: str = "http://ai-service:8002"


settings = Settings()
