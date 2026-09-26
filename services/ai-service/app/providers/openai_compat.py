"""
OpenAI-compatible provider.

Works with any provider that exposes an OpenAI-compatible REST API
(OpenAI, Azure OpenAI, Together, Groq, local vLLM, etc.).
Configure via environment variables:
  AI_PROVIDER=openai
  AI_API_KEY=sk-...
  AI_BASE_URL=https://api.openai.com/v1   (or your endpoint)
  AI_MODEL_REASONING=gpt-4o
  AI_MODEL_EMBEDDING=text-embedding-3-small
"""

from __future__ import annotations

from .base import BaseLLMProvider, LLMResponse
from shared.config import get_settings


class OpenAICompatibleProvider(BaseLLMProvider):

    def __init__(self):
        self._settings = get_settings()

    @property
    def name(self) -> str:
        return "openai-compatible"

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        import httpx
        s = self._settings
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{s.ai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {s.ai_api_key}"},
                json={
                    "model": s.ai_model_reasoning,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=data.get("model", s.ai_model_reasoning),
                provider="openai-compatible",
                tokens_used=data.get("usage", {}).get("total_tokens"),
            )

    async def embed(self, text: str) -> list[float]:
        import httpx
        s = self._settings
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{s.ai_base_url}/embeddings",
                headers={"Authorization": f"Bearer {s.ai_api_key}"},
                json={"model": s.ai_model_embedding, "input": text},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
