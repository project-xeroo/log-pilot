from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://logpilot:logpilot@postgres:5432/logpilot"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    ai_service_url: str = "http://ai-service:8001"
    forecasting_service_url: str = "http://forecasting-service:8002"
    audit_service_url: str = "http://audit-service:8003"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
