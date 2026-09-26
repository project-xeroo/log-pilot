from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://logpilot:logpilot@postgres:5432/logpilot"

    # Weight adjustment hyperparameters
    # Learning rate: how much each outcome moves the weight
    weight_learning_rate: float = 0.05
    # Minimum / maximum weight bounds
    weight_min: float = 0.1
    weight_max: float = 5.0


settings = Settings()
