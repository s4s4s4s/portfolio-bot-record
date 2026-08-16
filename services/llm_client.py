"""Async LLM клиент: Groq (приоритет) → Ollama (fallback).

Протокол `LLMClient` позволяет подменить реализацию в тестах.

Groq использует OpenAI-compatible HTTP API (библиотека `groq`).
Ollama — локальный HTTP endpoint.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol, cast, runtime_checkable

from core.config import get_settings
from core.logging import get_logger

log = get_logger()

DEFAULT_GROQ_MODEL = "qwen/qwen3-32b"
DEFAULT_OLLAMA_MODEL = "qwen2.5:14b"

_OLLAMA_PROC: asyncio.subprocess.Process | None = None


@runtime_checkable
class LLMClient(Protocol):
    async def chat(self, system: str, user: str, *, temperature: float = 0.3) -> str: ...


class GroqClient(LLMClient):
    """Groq Cloud API через httpx (легче тестировать чем `groq`-SDK)."""

    def __init__(self, api_key: str, model: str = DEFAULT_GROQ_MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._base = "https://api.groq.com/openai/v1"

    @staticmethod
    def _chat_body(
        model: str,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        low = model.lower()
        if "qwen" in low and "3" in low:
            body["reasoning_effort"] = "none"
        return body

    async def chat(self, system: str, user: str, *, temperature: float = 0.3) -> str:
        import httpx  # local import → easy to mock

        body = self._chat_body(self._model, system, user, temperature=temperature)
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"{self._base}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=body,
                )
                r.raise_for_status()
                data = r.json()
                return cast(str, data["choices"][0]["message"]["content"])
        except Exception:
            log.exception("Groq chat failed, will try Ollama fallback")
            return await _ollama_fallback(system, user, temperature=temperature)


class OllamaClient(LLMClient):
    """Локальный Ollama."""

    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base = base_url.rstrip("/")

    async def chat(self, system: str, user: str, *, temperature: float = 0.3) -> str:
        import httpx

        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(
                    f"{self._base}/api/chat",
                    json=body,
                )
                r.raise_for_status()
                data = r.json()
                return cast(str, data["message"]["content"])
        except Exception:
            log.exception("Ollama fallback also failed")
            return ""


async def _ensure_ollama_running() -> None:
    """Проверяет доступность Ollama; если нет — запускает `ollama serve`."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                return
    except Exception:
        pass

    log.warning("Ollama не отвечает, запускаем `ollama serve`...")
    global _OLLAMA_PROC
    env = os.environ.copy()
    env["OLLAMA_NUM_GPU"] = "999"
    try:
        _OLLAMA_PROC = await asyncio.create_subprocess_exec(
            "ollama", "serve",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        # Ждём пока сервер поднимется (до 10 сек)
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(timeout=2) as c:
                    r = await c.get("http://localhost:11434/api/tags")
                    if r.status_code == 200:
                        log.info("Ollama запущена.")
                        return
            except Exception:
                continue
        log.error("Ollama не поднялась за 10 сек.")
    except Exception:
        log.exception("Не удалось запустить ollama serve")


async def _ollama_fallback(system: str, user: str, *, temperature: float) -> str:
    await _ensure_ollama_running()
    settings = get_settings()
    client = OllamaClient(model=settings.ollama_model or DEFAULT_OLLAMA_MODEL)
    return await client.chat(system, user, temperature=temperature)


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Singleton-фабрика: Groq если ключ есть, иначе Ollama."""
    global _llm_client
    if _llm_client is None:
        settings = get_settings()
        if settings.groq_api_key:
            model = settings.groq_model or DEFAULT_GROQ_MODEL
            log.info("LLM: Groq model={model}", model=model)
            _llm_client = GroqClient(
                api_key=settings.groq_api_key,
                model=model,
            )
        else:
            model = settings.ollama_model or DEFAULT_OLLAMA_MODEL
            log.warning("GROQ_API_KEY пуст → Ollama model={model}", model=model)
            _llm_client = OllamaClient(model=model)
    return _llm_client


def reset_llm_client() -> None:
    """Для тестов: сбросить кэш и заново пикнуть реализацию."""
    global _llm_client
    _llm_client = None
