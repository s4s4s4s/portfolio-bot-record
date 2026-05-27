"""Текстовое подтверждение на шаге confirm."""
from __future__ import annotations

from services.booking_confirm import looks_like_confirm_no, looks_like_confirm_yes


def test_confirm_yes_phrases() -> None:
    assert looks_like_confirm_yes("да")
    assert looks_like_confirm_yes("дпа")
    assert looks_like_confirm_yes("все верно")
    assert looks_like_confirm_yes("Всё верно")
    assert looks_like_confirm_yes("подтверждаю")
    assert looks_like_confirm_yes("да, записывай")


def test_confirm_yes_rejects_cancel() -> None:
    assert not looks_like_confirm_yes("отмена")
    assert not looks_like_confirm_yes("не надо")


def test_confirm_yes_rejects_unrelated() -> None:
    assert not looks_like_confirm_yes("когда работаете?")
    assert not looks_like_confirm_yes("")


def test_confirm_no_phrases() -> None:
    assert looks_like_confirm_no("нет")
    assert looks_like_confirm_no("неа")
    assert looks_like_confirm_no("отмени")
    assert looks_like_confirm_no("не надо")
    assert looks_like_confirm_no("нет, не так")


def test_confirm_no_rejects_yes() -> None:
    assert not looks_like_confirm_no("да")
    assert not looks_like_confirm_no("всё верно")
