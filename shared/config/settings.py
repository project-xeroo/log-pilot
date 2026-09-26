from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # ── AI provider (provider-agnostic stub) ──────────────────────────────────
    ai_provider: str = "stub"          # stub | openai | anthropic | etc.
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model_reasoning: str = "gpt-4o"
    ai_model_embedding: str = "text-embedding-3-small"
    ai_embedding_dimensions: int = 1536

    # ── Forecasting loop ──────────────────────────────────────────────────────
    forecasting_loop_interval_seconds: int = 60
    forecasting_velocity_window_count: int = 10   # how many past windows to look back
    forecasting_warning_threshold: float = 60.0
    forecasting_critical_threshold: float = 80.0

    # Risk score weights (must sum to 1.0)
    weight_velocity: float = 0.30
    weight_similarity: float = 0.40
    weight_baseline: float = 0.30

    # ── Autonomy defaults ─────────────────────────────────────────────────────
    default_autonomy_tier: str = "propose"   # observe | propose | auto

    # ── Auth ──────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # ── Service identity ──────────────────────────────────────────────────────
    service_name: str = "logpilot"
    environment: str = "development"

    # ── Analysis layer (Phase 3) ──────────────────────────────────────────────
    # Deduplication
    dedup_similarity_threshold: float = 0.85   # cosine similarity threshold

    # Clustering
    clustering_min_samples: int = 2            # DBSCAN min_samples
    clustering_eps: float = 0.25              # DBSCAN eps in cosine space

    # Anomaly detection
    anomaly_zscore_threshold: float = 3.0     # z-score above baseline = anomaly


@lru_cache
def get_settings() -> Settings:
    return Settings()
