"""Текстовые запросы во время активной записи (дата, время, ожидание)."""
from __future__ import annotations

import re

_NAME_BLOCKLIST = frozenset({
    "сперма", "хуй", "хуя", "бля", "ебан", "ебал", "пизд", "сука",
})


def safe_client_first_name(full_name: str) -> str | None:
    part = (full_name or "").strip().split()[0] if full_name else ""
    if len(part) < 2 or len(part) > 30:
        return None
    low = part.lower()
    if low in _NAME_BLOCKLIST:
        return None
    if not re.fullmatch(r"[а-яёa-z\-]+", low, re.IGNORECASE):
        return None
    return part


def looks_like_date_correction(text: str) -> bool:
    low = text.lower()
    return any(
        p in low
        for p in (
            "послезавтра", "завтра", "сегодня", "я же сказал", "имел в виду",
            "имела в виду", "другой день", "на послезавтра",
        )
    )


def looks_like_later_time_request(text: str) -> bool:
    low = text.lower()
    if any(p in low for p in ("позже", "попозже", "после ", "побольше", "подольше")):
        return True
    if "нельзя" in low and re.search(r"\d{1,2}\s*[:.]?\s*\d{0,2}", low):
        return True
    return False


def looks_like_waitlist_request(text: str) -> bool:
    low = text.lower()
    return any(
        p in low
        for p in (
            "сообщите", "сообщи", "напишите", "напиши", "уведом",
            "освобод", "если появ", "если будет", "напомн",
        )
    )


def parse_min_time_hint(text: str) -> str | None:
    """Минимальное желаемое время «позже 17 30» → 17:30 для сравнения."""
    low = text.lower()
    m = re.search(r"(\d{1,2})\s*[:.]?\s*(\d{2})", low)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"(?:после|позже)\s*(\d{1,2})(?:\s*[:.]?\s*(\d{2}))?", low)
    if m:
        mi = m.group(2) or "00"
        return f"{int(m.group(1)):02d}:{mi}"
    return None
