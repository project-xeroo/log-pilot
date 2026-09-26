"""
Tests for the model-agnostic provider layer.
Uses respx to mock HTTP calls — no real API key needed.
"""
from __future__ import annotations

import pytest
import respx
from httpx import Response


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the shared client singleton between tests."""
    import app.providers.cloud as cloud_module
    cloud_module._client = None
    yield
    cloud_module._client = None


@respx.mock
@pytest.mark.asyncio
async def test_embed_returns_vectors():
    """EmbeddingProvider.embed() returns one vector per input text."""
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"

    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"index": 0, "object": "embedding", "embedding": [0.1] * 1536},
                    {"index": 1, "object": "embedding", "embedding": [0.2] * 1536},
                ],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            },
        )
    )

    from app.providers import EmbeddingProvider
    provider = EmbeddingProvider()
    vectors = await provider.embed(["hello world", "another line"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1536
    assert vectors[0][0] == pytest.approx(0.1)


@respx.mock
@pytest.mark.asyncio
async def test_embed_empty_returns_empty():
    """EmbeddingProvider.embed([]) short-circuits without an API call."""
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"

    from app.providers import EmbeddingProvider
    provider = EmbeddingProvider()
    result = await provider.embed([])
    assert result == []


@respx.mock
@pytest.mark.asyncio
async def test_chat_complete_returns_string():
    """ChatProvider.complete() returns the model's response text."""
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"

    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Log analysis result."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            },
        )
    )

    from app.providers import ChatProvider
    provider = ChatProvider()
    result = await provider.complete(
        messages=[{"role": "user", "content": "Explain this error."}]
    )
    assert result == "Log analysis result."


@pytest.mark.asyncio
async def test_stub_fallback_without_api_key(monkeypatch):
    """With no API key, chat and embeddings degrade to the offline stub."""
    from app.config import settings
    from app.providers import ChatProvider, EmbeddingProvider, StubProvider, get_provider

    monkeypatch.setattr(settings, "openai_api_key", "")

    vectors = await EmbeddingProvider().embed(["a", "b"])
    assert len(vectors) == 2 and len(vectors[0]) == 1536

    chat = ChatProvider()
    assert chat.model == "stub-1.0"
    assert "Stub response" in await chat.complete([{"role": "user", "content": "hi"}])
    assert isinstance(get_provider(), StubProvider)
