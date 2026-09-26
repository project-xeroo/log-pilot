from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg2://logpilot:logpilot@localhost:5432/logpilot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Service URLs (inter-service calls)
    ai_service_url: str = "http://ai-service:8001"
    forecasting_service_url: str = "http://forecasting-service:8002"
    audit_service_url: str = "http://audit-service:8003"
