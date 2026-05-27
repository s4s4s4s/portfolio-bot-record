"""Тесты нормализации телефона."""
from __future__ import annotations

import pytest

from services.phone import is_valid_phone, normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("+79051234567", "+79051234567"),
    ("+7 905 123 45 67", "+79051234567"),
    ("8 (905) 123-45-67", "+79051234567"),
    ("8-905-123-45-67", "+79051234567"),
    ("89051234567", "+79051234567"),
    ("79051234567", "+79051234567"),
    ("9153108217", "+79153108217"),
    ("+7.905.123.45.67", "+79051234567"),
    ("+7\u00A0905\u00A0123\u00A045\u00A067", "+79051234567"),
    ("+74951234567", "+74951234567"),
    ("+7 (495) 123-45-67", "+74951234567"),
    ("84951234567", "+74951234567"),
    ("+78121234567", "+78121234567"),
    ("8 800 555 35 35", "+78005553535"),
    ("88005553535", "+78005553535"),
    ("+88005553535", "+78005553535"),
    ("8005553535", "+78005553535"),
    ("+7 800 555 35 35", "+78005553535"),
    ("+8 905 123 45 67", "+79051234567"),
])
def test_normalize_phone_valid(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    "abcd",
    "12345",
    "999",
    "+7 905 12345",
    "+7 905 1234567890",
    None,
    "  ",
    "+7 0",
    "12345678901",
    "0123456789",
])
def test_normalize_phone_invalid(raw: str | None) -> None:
    assert normalize_phone(raw) is None  # type: ignore[arg-type]


def test_is_valid_phone_helpers() -> None:
    assert is_valid_phone("+79051234567") is True
    assert is_valid_phone("8 800 555 35 35") is True
    assert is_valid_phone("invalid") is False
    assert is_valid_phone("") is False
