<<<<<<< HEAD
=======
"""API Gateway configuration."""
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

<<<<<<< HEAD
    database_url: str = "postgresql+psycopg2://logpilot:logpilot@postgres:5432/logpilot"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    ai_service_url: str = "http://ai-service:8001"
    forecasting_service_url: str = "http://forecasting-service:8002"
    audit_service_url: str = "http://audit-service:8003"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
=======
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
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0


settings = Settings()
