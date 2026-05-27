"""Нормализация российского номера → +7 и 10 цифр национального номера."""

from __future__ import annotations

import re

_DIGITS_RE = re.compile(r"\D")

PHONE_HINT = "ваш номер телефона"


def _extract_digits(raw: str) -> str:
    return _DIGITS_RE.sub("", raw)


def normalize_phone(raw: str | None) -> str | None:
    """Мобильный, городской, 8-800 — любой ввод с 8/+7/7 и 10 цифрами NSN."""
    if not raw or not isinstance(raw, str):
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None

    digits = _extract_digits(trimmed)
    if not digits or not digits.isdigit():
        return None

    national: str | None = None

    if len(digits) == 10:
        national = digits
    elif len(digits) == 11 and digits[0] in ("7", "8"):
        national = digits[1:]
    else:
        return None

    if len(national) != 10:
        return None

    # Российский NSN: 3–9 (мобильные 9xx, городские 3xx/4xx/8xx, бесплатные 800…)
    if national[0] not in "3456789":
        return None

    return f"+7{national}"


def is_valid_phone(raw: str | None) -> bool:
    return normalize_phone(raw) is not None


async def phone_error_message(*, attempt: int = 0) -> str:
    from services.persona import phone_invalid_error

    return await phone_invalid_error(attempt=attempt)
