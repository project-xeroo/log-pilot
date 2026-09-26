"""
Stub LLM provider.

Returns deterministic template-based responses so the full forecasting
pipeline can run end-to-end without a live API key configured.
Set AI_PROVIDER=stub in .env (the default).
"""

from __future__ import annotations

import hashlib
import math

from .base import BaseLLMProvider, LLMResponse


class StubProvider(BaseLLMProvider):
    """Template-based stub — no external calls, no API key required."""

    @property
    def name(self) -> str:
        return "stub"

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        # Produce a deterministic but contextually flavoured stub response
        digest = hashlib.md5(prompt.encode()).hexdigest()[:8]
        content = (
            f"[Stub response — replace AI_PROVIDER in .env to use a real model] "
            f"Analysis of the provided log context yields no additional insight "
            f"beyond the threshold-based signals. Reference ID: {digest}."
        )
        return LLMResponse(
            content=content,
            model="stub-1.0",
            provider="stub",
            tokens_used=len(prompt.split()),
        )

    async def embed(self, text: str) -> list[float]:
        """
        Deterministic pseudo-embedding based on a hash of the input text.
        Dimension = 1536 (matches text-embedding-3-small).
        Not semantically meaningful — for structural testing only.
        """
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
        dims = 1536
        result: list[float] = []
        for i in range(dims):
            val = math.sin(seed + i) * 0.5
            result.append(round(val, 6))
        return result
