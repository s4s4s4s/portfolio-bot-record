"""Разбор запросов на несколько записей в одном сообщении."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from services.booking_cancel import looks_like_my_bookings
from services.service_aliases import DEFAULT_ALIASES, normalize_service_hint


@dataclass(frozen=True)
class BookingSegment:
    service_name: str
    date_hint: str
    date_label: str


def _date_from_chunk(chunk: str, *, today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    low = chunk.lower()
    if "послезавтра" in low:
        d = today + timedelta(days=2)
        return d.isoformat(), d.strftime("%d.%m")
    if "завтра" in low:
        d = today + timedelta(days=1)
        return d.isoformat(), d.strftime("%d.%m")
    if "сегодня" in low:
        return today.isoformat(), today.strftime("%d.%m")
    return "", ""


def _match_service_in_chunk(chunk: str, service_names: list[str]) -> str | None:
    low = chunk.lower()
    for name in service_names:
        nl = name.lower()
        if nl in low or low in nl:
            return name
        stem = nl.split("(")[0].strip()
        if len(stem) >= 4 and stem in low:
            return name
    for alias, canonical in DEFAULT_ALIASES.items():
        if alias in low:
            hint = normalize_service_hint(canonical)
            for name in service_names:
                if hint.lower() in name.lower() or name.lower().startswith(hint.lower()[:5]):
                    return name
    keywords = (
        ("массаж", "массаж"),
        ("маникюр", "маникюр"),
        ("стриж", "стриж"),
    )
    for key, stem in keywords:
        if key in low:
            for name in service_names:
                if stem in name.lower():
                    return name
    return None


def _split_chunks(text: str) -> list[str]:
    low = text.lower()
    parts = re.split(
        r"\s*,\s*|\s+а\s+|\s+и\s+(?=(?:на\s+)?(?:завтра|послезавтра|сегодня))",
        low,
    )
    return [p.strip() for p in parts if p.strip()]


def extract_booking_segments(text: str, service_names: list[str]) -> list[BookingSegment]:
    """«завтра массаж, послезавтра маникюр» → два сегмента."""
    if not text or not service_names:
        return []
    chunks = _split_chunks(text)
    if len(chunks) < 2:
        return []
    segments: list[BookingSegment] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        svc = _match_service_in_chunk(chunk, service_names)
        iso, label = _date_from_chunk(chunk)
        if not svc or not iso:
            continue
        key = (svc, iso)
        if key in seen:
            continue
        seen.add(key)
        segments.append(BookingSegment(service_name=svc, date_hint=iso, date_label=label))
    return segments


def looks_like_booking_request(text: str, service_names: list[str]) -> bool:
    low = text.lower()
    if looks_like_my_bookings(text):
        return False
    if any(
        w in low
        for w in (
            "запиш", "запиши", "запишите", "записаться", "хочу", "давай", "давайте",
            "нужен", "нужна", "записать", "можно",
        )
    ):
        return True
    has_svc = _match_service_in_chunk(low, service_names) is not None
    has_date = any(d in low for d in ("завтра", "послезавтра", "сегодня"))
    return has_svc and has_date
