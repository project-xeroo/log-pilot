"""
Cloud AI client layer (OpenAI-compatible).

All cloud AI calls (embeddings + chat completions) go through this module.
The rest of the codebase calls EmbeddingProvider and ChatProvider — never the
OpenAI client directly — so the underlying model or vendor can be swapped by
changing config values alone.

When no API key is configured (or AI_PROVIDER=stub) both providers fall back
to the deterministic StubProvider, so search and chat keep working offline.

Supports any OpenAI-compatible REST endpoint:
  - OpenAI (default)
  - Azure OpenAI (set OPENAI_BASE_URL to your Azure endpoint)
  - Any other provider with an OpenAI-compatible API
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import structlog
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

from app.config import settings
from .stub import StubProvider

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Shared OpenAI-compatible async client (singleton, reused across requests)
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Return (and lazily create) the shared async OpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.provider_timeout_seconds,
            max_retries=0,  # We handle retries ourselves via tenacity
        )
    return _client


# ---------------------------------------------------------------------------
# Retry decorator — applied to every outbound AI API call
# ---------------------------------------------------------------------------

_RETRYABLE = (RateLimitError, APITimeoutError, APIError)

_retry_policy = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(settings.provider_max_retries),
    wait=wait_exponential(
        multiplier=settings.provider_retry_wait_seconds,
        min=settings.provider_retry_wait_seconds,
        max=10.0,
    ),
    before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Embedding Provider
# ---------------------------------------------------------------------------

class EmbeddingProvider:
    """
    Generates embeddings using the configured cloud embedding model.

    Usage:
        provider = EmbeddingProvider()
        vectors = await provider.embed(["log line 1", "log line 2"])
    """

    def __init__(self) -> None:
        self._stub = StubProvider() if settings.use_stub_provider else None
        self._client = None if self._stub else get_client()
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts. Returns one float vector per input text.
        Preserves input order.
        """
        if not texts:
            return []
        if self._stub:
            return [await self._stub.embed(t or "") for t in texts]
        return await self._embed_remote(texts)

    @_retry_policy
    async def _embed_remote(self, texts: list[str]) -> list[list[float]]:
        # Truncate any individual text to avoid exceeding model token limits.
        # text-embedding-3-small supports up to 8191 tokens; we conservatively
        # cap at 2000 characters (well under the token limit for log messages).
        texts = [t[:2000] if t else "" for t in texts]

        log.debug(
            "provider.embed.request",
            model=self._model,
            count=len(texts),
        )

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )

        # API returns results in the same order as input
        vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

        log.debug(
            "provider.embed.response",
            model=self._model,
            count=len(vectors),
            usage=response.usage.total_tokens if response.usage else None,
        )

        return vectors

    async def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for embedding a single text."""
        results = await self.embed([text])
        return results[0]


# ---------------------------------------------------------------------------
# Chat Provider
# ---------------------------------------------------------------------------

class ChatProvider:
    """
    Calls the configured fast reasoning model for conversational chat responses.

    Usage (non-streaming):
        provider = ChatProvider()
        text = await provider.complete(messages=[...])

    Usage (streaming):
        async for token in provider.stream(messages=[...]):
            yield token
    """

    def __init__(self, *, model: str | None = None) -> None:
        self._stub = StubProvider() if settings.use_stub_provider else None
        self._client = None if self._stub else get_client()
        self._model = model or settings.chat_model

    @property
    def model(self) -> str:
        return "stub-1.0" if self._stub else self._model

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Send a chat completion request and return the full response text.
        Retries on transient errors.
        """
        if self._stub:
            return (await self._stub.complete(_flatten(messages))).content
        return await self._complete_remote(messages, max_tokens=max_tokens, temperature=temperature)

    @_retry_policy
    async def _complete_remote(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        log.debug(
            "provider.chat.request",
            model=self._model,
            message_count=len(messages),
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens or settings.chat_max_response_tokens,
            temperature=temperature if temperature is not None else settings.chat_temperature,
            stream=False,
        )

        content = response.choices[0].message.content or ""

        log.debug(
            "provider.chat.response",
            model=self._model,
            usage=response.usage.total_tokens if response.usage else None,
            finish_reason=response.choices[0].finish_reason,
        )

        return content

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a chat completion response, yielding tokens as they arrive.
        Does NOT use the tenacity retry decorator — streaming connections that
        fail mid-stream surface the error to the caller directly.
        """
        if self._stub:
            yield (await self._stub.complete(_flatten(messages))).content
            return

        log.debug(
            "provider.chat.stream_request",
            model=self._model,
            message_count=len(messages),
        )

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens or settings.chat_max_response_tokens,
            temperature=temperature if temperature is not None else settings.chat_temperature,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


def _flatten(messages: list[dict]) -> str:
    return " ".join(str(m.get("content", "")) for m in messages)
