"""Unit тесты для NLU-слоя."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.nlu import _best_match, _resolve_date, classify_intent, generate_greeting_reply
from services.salon_time import salon_today


class MockLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._calls: list[tuple[str, str]] = []

    async def chat(self, system: str, user: str, *, temperature: float = 0.3) -> str:
        self._calls.append((system, user))
        return self._responses.pop(0) if self._responses else ""


@pytest.mark.asyncio
async def test_classify_intent_book():
    m = MockLLMClient(['{"intent":"book","entities":{"service_name":"стрижка"}}'])
    result = await classify_intent("Хочу записаться на стрижку", m)
    assert result["intent"] == "book"
    assert result["entities"]["service_name"] == "стрижка"


@pytest.mark.asyncio
async def test_classify_intent_empty_defaults():
    m = MockLLMClient([""])
    result = await classify_intent("test", m)
    assert result["intent"] == "other"


@pytest.mark.asyncio
async def test_classify_intent_strips_markdown():
    raw = '```json\n{"intent":"help","entities":{}}\n```'
    m = MockLLMClient([raw])
    result = await classify_intent("help", m)
    assert result["intent"] == "help"


@pytest.mark.asyncio
async def test_generate_greeting_reply():
    m = MockLLMClient(["Привет! Запишемся? 😊"])
    text = await generate_greeting_reply(
        "Привет", m, services=["Маникюр"], masters=["Анна"],
    )
    assert "Привет" in text or "Запис" in text


class TestResolveDate:
    def test_tomorrow(self):
        assert _resolve_date("завтра") == salon_today() + timedelta(days=1)

    def test_day_after_day_after_tomorrow(self):
        assert _resolve_date("послепослезавтра") == salon_today() + timedelta(days=3)

    def test_posleposlezavtra_not_tomorrow(self):
        assert _resolve_date("послепослезавтра") != salon_today() + timedelta(days=1)

    def test_posle_poslezavtra(self):
        assert _resolve_date("после послезавтра") == salon_today() + timedelta(days=3)

    def test_posleposlezavtra(self):
        assert _resolve_date("послезавтра") == salon_today() + timedelta(days=2)

    def test_today(self):
        assert _resolve_date("сегодня") == salon_today()

    def test_ddmm_future(self):
        future = salon_today().replace(year=salon_today().year + 1)
        assert _resolve_date(future.strftime("%d.%m.%Y")) == future

    def test_past_returns_none(self):
        assert _resolve_date("15.06.2020") is None

    def test_empty(self):
        assert _resolve_date("") is None


class TestBestMatch:
    def test_exact(self):
        assert _best_match("анна", ["Анна", "Дмитрий"]) == "Анна"

    def test_contains(self):
        assert _best_match("стриж", ["Стрижка (без окрашивания)", "Маникюр"]) == "Стрижка (без окрашивания)"

    def test_none(self):
        assert _best_match("foo", []) is None
