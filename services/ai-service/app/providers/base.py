"""
Provider-agnostic LLM interface.

Defines the abstract contract every provider must implement.
Drop in any provider by setting AI_PROVIDER in .env.
Currently ships with a StubProvider that returns template-based responses
so the system is fully functional without a real API key.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    tokens_used: int | None = None


class BaseLLMProvider(ABC):
    """Abstract contract for all LLM providers."""

    @abstractmethod
    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Send a completion prompt and return the response."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
