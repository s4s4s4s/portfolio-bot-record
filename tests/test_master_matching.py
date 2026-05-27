"""Сопоставление имён мастеров."""
from __future__ import annotations

from services.master_matching import (
    extract_master_hints,
    find_master_in_text,
    find_master_name,
    master_matches_hint,
    master_matches_text,
)


def test_dima_dative_matches_dmitry() -> None:
    assert master_matches_hint("Дмитрий", "диме")
    assert find_master_name("диме", ["Анна", "Дмитрий"]) == "Дмитрий"


def test_dmitry_genitive_in_cancel_phrase() -> None:
    assert master_matches_text("Дмитрий", "отмени дмитрия")


def test_extract_k_dime() -> None:
    assert extract_master_hints("запиши на маникюр к диме на завтра") == ["диме"]


def test_find_master_in_booking_phrase() -> None:
    text = "запиши меня на маникюр к диме на завтра 18 00"
    assert find_master_in_text(text, ["Анна", "Дмитрий"]) == "Дмитрий"


def test_anna_diminutive_anya() -> None:
    assert find_master_name("аня", ["Анна", "Дмитрий"]) == "Анна"
    assert find_master_in_text("Аня", ["Анна", "Дмитрий"]) == "Анна"
