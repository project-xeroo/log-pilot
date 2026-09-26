"""AI Service configuration."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "ai-service"
    debug: bool = False

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot"
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # ── Redis (Agent Feed live events) ───────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Cloud AI provider (OpenAI-compatible) ────────────────────────────────
    # "stub" (or an empty API key) runs without a real model: deterministic
    # template answers and pseudo-embeddings (PRD §8.3 graceful degradation).
    ai_provider: str = Field("openai", validation_alias=AliasChoices("AI_PROVIDER"))
    # Point base_url at any OpenAI-compatible endpoint (Azure OpenAI, proxies, …)
    openai_api_key: str = Field("", validation_alias=AliasChoices("OPENAI_API_KEY", "AI_API_KEY"))
    openai_base_url: str = Field(
        "https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "AI_BASE_URL"),
    )

    # Model assignments (PRD §6.1) — swap without code changes
    embedding_model: str = Field(
        "text-embedding-3-small",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "AI_MODEL_EMBEDDING"),
    )
    # Fast reasoning model: chat, search responses, log explanations
    chat_model: str = Field("gpt-4o-mini", validation_alias=AliasChoices("CHAT_MODEL", "OPENAI_FAST_MODEL"))
    # Deep reasoning model: RCA, incident reports, pre-mortems
    reasoning_model: str = Field(
        "gpt-4o",
        validation_alias=AliasChoices("REASONING_MODEL", "OPENAI_MODEL", "AI_MODEL_REASONING"),
    )
    reasoning_max_tokens: int = Field(
        4096, validation_alias=AliasChoices("REASONING_MAX_TOKENS", "OPENAI_MAX_TOKENS")
    )

    # ── Reports ──────────────────────────────────────────────────────────────
    report_prompt_version: str = "v1"

    # ── Embedding settings ───────────────────────────────────────────────────
    embedding_batch_size: int = 256          # records per embedding API call
    embedding_dimensions: int = 1536         # must match vector(1536) column in Phase 1 schema

    # ── Search settings ──────────────────────────────────────────────────────
    semantic_search_top_k: int = 20          # k-NN neighbours to retrieve
    keyword_search_limit: int = 100          # max rows from FTS query
    search_max_results: int = 100            # hard cap returned to caller

    # ── Chat settings ────────────────────────────────────────────────────────
    chat_context_top_k: int = 8             # log records injected as context
    chat_max_context_tokens: int = 6000     # token budget for retrieved context
    chat_max_response_tokens: int = 1024    # max tokens in model response
    chat_temperature: float = 0.2           # low temp for factual, sourced answers

    # ── Provider retry policy ────────────────────────────────────────────────
    provider_max_retries: int = 3
    provider_retry_wait_seconds: float = 1.0
    provider_timeout_seconds: float = 30.0

    @property
    def use_stub_provider(self) -> bool:
        return self.ai_provider == "stub" or not self.openai_api_key


settings = Settings()
