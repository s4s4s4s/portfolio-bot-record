"""Эталонные примеры сцен: подстановка фактов и guard битых фраз."""
from __future__ import annotations

from services.human_reply import (
    _example_fallback,
    _fill_example,
    reply_phrase_broken,
)


def test_fill_example_phone_with_name() -> None:
    text = _fill_example(
        "{first_name}, оставьте номер телефона для связи",
        {"first_name": "Фатима"},
    )
    assert text == "Фатима, оставьте номер телефона для связи"


def test_fill_example_phone_without_name() -> None:
    text = _fill_example(
        "{first_name}, оставьте номер телефона для связи",
        {},
    )
    assert text == "Оставьте номер телефона для связи"


def test_fill_example_slot_time() -> None:
    text = _fill_example("На {time} — отлично. Как к вам обращаться?", {"time": "16:00"})
    assert "16:00" in text
    assert "?" in text


def test_reply_phrase_broken_detects_incomplete() -> None:
    assert reply_phrase_broken("спасибо что выбрали наш можете сказать номер", scene="enter_phone")
    assert not reply_phrase_broken("Фатима, оставьте номер телефона для связи", scene="enter_phone")


def test_reply_phrase_broken_rejects_na_kakuyu_zapis() -> None:
    assert reply_phrase_broken("На какую запись отменить?", scene="cancel_which")
    assert not reply_phrase_broken("Какую запись отменить?", scene="cancel_which")


def test_example_fallback_enter_phone() -> None:
    text = _example_fallback("enter_phone", {"first_name": "Фатима"})
    assert "Фатима" in text
    assert "телефон" in text.lower()
