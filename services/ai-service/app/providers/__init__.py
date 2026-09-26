"""
Model-agnostic provider layer (PRD §6).

Two entry points, one configuration (``app.config``):
  - EmbeddingProvider / ChatProvider — embeddings and the fast reasoning model
    (search, chat); see ``cloud.py``.
  - get_provider() — a BaseLLMProvider backed by the deep reasoning model
    (RCA, incident reports, pre-mortems).

Both fall back to the deterministic StubProvider when AI_PROVIDER=stub or no
API key is configured.
"""
from __future__ import annotations

from app.config import settings
from .base import BaseLLMProvider, LLMResponse
from .stub import StubProvider
from .cloud import ChatProvider, EmbeddingProvider, get_client
from .openai_compat import OpenAICompatibleProvider

_OPENAI_COMPATIBLE = ("openai", "openai-compatible", "azure", "groq", "together")


def get_provider() -> BaseLLMProvider:
    """Factory: return the configured deep-reasoning provider instance."""
    if settings.use_stub_provider:
        return StubProvider()
    if settings.ai_provider in _OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider()
    raise ValueError(f"Unknown AI provider: '{settings.ai_provider}'. Set AI_PROVIDER in .env.")


__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "StubProvider",
    "OpenAICompatibleProvider",
    "ChatProvider",
    "EmbeddingProvider",
    "get_client",
    "get_provider",
]
