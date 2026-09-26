"""
OpenAI-compatible provider for the deep-reasoning tools (RCA, reports, pre-mortems).

Works with any provider that exposes an OpenAI-compatible REST API
(OpenAI, Azure OpenAI, Together, Groq, local vLLM, etc.). It shares the
client, credentials, and retry policy of the chat/search layer in
``providers.cloud`` and uses the deep reasoning model (PRD §6.1).
Configure via environment variables:
  OPENAI_API_KEY / OPENAI_BASE_URL   (AI_API_KEY / AI_BASE_URL also accepted)
  REASONING_MODEL=gpt-4o
  EMBEDDING_MODEL=text-embedding-3-small
"""

from __future__ import annotations

from app.config import settings
from .base import BaseLLMProvider, LLMResponse
from .cloud import ChatProvider, EmbeddingProvider


class OpenAICompatibleProvider(BaseLLMProvider):

    def __init__(self):
        self._chat = ChatProvider(model=settings.reasoning_model)
        self._embedder = EmbeddingProvider()

    @property
    def name(self) -> str:
        return "openai-compatible"

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        content = await self._chat.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=min(max_tokens, settings.reasoning_max_tokens),
        )
        return LLMResponse(content=content, model=self._chat.model, provider=self.name)

    async def embed(self, text: str) -> list[float]:
        return await self._embedder.embed_one(text)
