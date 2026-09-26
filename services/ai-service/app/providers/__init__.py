from .base import BaseLLMProvider, LLMResponse
from .stub import StubProvider
from .openai_compat import OpenAICompatibleProvider
from shared.config import get_settings


def get_provider() -> BaseLLMProvider:
    """Factory: return the configured LLM provider instance."""
    provider = get_settings().ai_provider
    if provider == "stub":
        return StubProvider()
    if provider in ("openai", "openai-compatible", "azure", "groq", "together"):
        return OpenAICompatibleProvider()
    raise ValueError(f"Unknown AI provider: '{provider}'. Set AI_PROVIDER in .env.")


__all__ = ["BaseLLMProvider", "LLMResponse", "StubProvider", "OpenAICompatibleProvider", "get_provider"]
