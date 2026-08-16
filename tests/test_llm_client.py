"""Tests for LLMClient factory + protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from services.llm_client import (
    GroqClient,
    OllamaClient,
    get_llm_client,
    reset_llm_client,
)


@runtime_checkable
class _LLMClientProtocol(Protocol):
    async def chat(self, system: str, user: str, *, temperature: float = 0.3) -> str: ...


@pytest.fixture(autouse=True)
def reset():
    reset_llm_client()
    yield
    reset_llm_client()


def test_groq_client_init():
    c = GroqClient("key")
    assert isinstance(c, _LLMClientProtocol)


def test_ollama_client_init():
    c = OllamaClient()
    assert isinstance(c, _LLMClientProtocol)


@pytest.mark.asyncio
async def test_groq_qwen3_disables_reasoning(monkeypatch):
    called = {}

    class FakeResponse:
        def raise_for_status(self): ...
        def json(self): return {"choices": [{"message": {"content": "привет"}}]}

    class FakeClient:
        def __init__(self, **kwargs): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *_): ...
        async def post(self, *_, **kwargs):
            called["body"] = kwargs.get("json")
            return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    c = GroqClient("testkey", model="qwen/qwen3-32b")
    result = await c.chat("sys", "user")
    assert result == "привет"
    assert called["body"]["model"] == "qwen/qwen3-32b"
    assert called["body"]["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_groq_client_calls_httpx(monkeypatch):
    called = {}

    class FakeResponse:
        def raise_for_status(self): ...
        def json(self): return {"choices": [{"message": {"content": "hi"}}]}

    class FakeClient:
        def __init__(self, **kwargs): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *_): ...
        async def post(self, *_, **kwargs):
            called["body"] = kwargs.get("json")
            return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    c = GroqClient("testkey", model="llama-3.3-70b-versatile")
    result = await c.chat("sys", "user")
    assert result == "hi"
    assert called["body"]["model"] == "llama-3.3-70b-versatile"
    assert "reasoning_effort" not in called["body"]


@pytest.mark.asyncio
async def test_ollama_client_calls_httpx(monkeypatch):
    called = {}

    class FakeResponse:
        def raise_for_status(self): ...
        def json(self): return {"message": {"content": "ola"}}

    class FakeClient:
        def __init__(self, **kwargs): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *_): ...
        async def post(self, *_, **kwargs):
            called["body"] = kwargs.get("json")
            return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    c = OllamaClient(model="qwen")
    result = await c.chat("s", "u")
    assert result == "ola"
    assert called["body"]["model"] == "qwen"


# Factory

@pytest.mark.asyncio
async def test_factory_groq_when_key_set(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    from core.config import reload_settings
    reload_settings()
    reset_llm_client()
    c = get_llm_client()
    assert isinstance(c, GroqClient)


@pytest.mark.asyncio
async def test_factory_ollama_when_no_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    from core.config import reload_settings
    reload_settings()
    reset_llm_client()
    c = get_llm_client()
    assert isinstance(c, OllamaClient)
