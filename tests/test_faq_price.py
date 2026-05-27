"""Тесты ответов на вопросы о цене."""
from __future__ import annotations

import pytest

from services.faq_price import (
    format_price_reply,
    looks_like_price_followup,
    looks_like_price_question,
    _resolve_service,
)
from services.human_reply import _SCENE_EXAMPLES, _fill_example

def test_price_question_detect() -> None:
    assert looks_like_price_question("Сколько у вас стоит стрижка?")
    assert looks_like_price_question("какая цена на маникюр")
    assert not looks_like_price_question("хочу на стрижку завтра")


def test_price_followup() -> None:
    assert looks_like_price_followup("Часик")
    assert looks_like_price_followup("да")
    assert looks_like_price_followup("запиши")
    assert not looks_like_price_followup("Сколько стоит маникюр?")


def test_resolve_service_from_text() -> None:
    class S:
        def __init__(self, name: str, duration_min: int = 60, price_kop: int = 150_000) -> None:
            self.name = name
            self.duration_min = duration_min
            self.price_kop = price_kop
            self.id = 1

    services = [S("Стрижка (без окрашивания)"), S("Маникюр")]
    hit = _resolve_service("Сколько у вас стоит стрижка?", services)
    assert hit is not None
    assert "Стрижка" in hit.name


def test_faq_price_one_example() -> None:
    text = _fill_example(
        _SCENE_EXAMPLES["faq_price_one"],
        {"service": "Стрижка", "duration": "60", "price": "1500"},
    )
    assert "1500" in text
    assert "Записать?" in text


@pytest.mark.asyncio
async def test_format_single_price() -> None:
    class S:
        name = "Стрижка (без окрашивания)"
        duration_min = 60
        price_kop = 150_000

    text = await format_price_reply([], target=S())
    assert "1500" in text or "faq_price_one" in text
