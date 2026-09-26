"""API Gateway configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@postgres:5432/logpilot"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # Downstream service URLs
    ingestion_service_url: str = "http://log-ingestion-service:8001"
    ai_service_url: str = "http://ai-service:8002"
    forecasting_service_url: str = "http://forecasting-service:8003"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
