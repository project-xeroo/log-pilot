"""API Gateway configuration."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@postgres:5432/logpilot"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # JWT (JWT_SECRET_KEY accepted for older .env files)
    jwt_secret: str = Field(
        "change-me-in-production",
        validation_alias=AliasChoices("JWT_SECRET", "JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600

    # Downstream service URLs
    ingestion_service_url: str = "http://log-ingestion-service:8001"
    ai_service_url: str = "http://ai-service:8002"
    forecasting_service_url: str = "http://forecasting-service:8003"
    audit_service_url: str = "http://audit-service:8005"

    # Redis (real-time event bus for the WebSocket)
    redis_url: str = "redis://redis:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
