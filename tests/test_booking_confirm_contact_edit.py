"""Правка имени и телефона на шаге confirm."""
from __future__ import annotations

from services.booking_confirm import (
    detect_confirm_contact_edit,
    looks_like_confirm_yes,
)


def test_detect_name_edit_phrase() -> None:
    kind, inline = detect_confirm_contact_edit("имя другое")
    assert kind == "name"
    assert inline is None


def test_detect_name_inline() -> None:
    kind, inline = detect_confirm_contact_edit("имя Фатима")
    assert kind == "name"
    assert inline == "Фатима"


def test_detect_phone_edit_phrase() -> None:
    kind, inline = detect_confirm_contact_edit("номер другой")
    assert kind == "phone"
    assert inline is None


def test_detect_phone_inline() -> None:
    kind, inline = detect_confirm_contact_edit("поменять телефон 9153108217")
    assert kind == "phone"
    assert inline == "+79153108217"


def test_confirm_yes_not_name_edit() -> None:
    assert not looks_like_confirm_yes("имя другое")
    assert looks_like_confirm_yes("да, всё верно")
