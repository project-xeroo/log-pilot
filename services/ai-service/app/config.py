from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096

    # Fallback model for cheaper draft iterations
    openai_fast_model: str = "gpt-4o-mini"

    report_prompt_version: str = "v1"


settings = Settings()
