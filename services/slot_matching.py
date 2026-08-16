"""Фильтрация слотов по времени и поиск ближайшего окна."""
from __future__ import annotations

from datetime import date, datetime, time

from db.models import Slot


def parse_time_hint(time_hint: str) -> tuple[int, int] | None:
    if not time_hint or ":" not in time_hint:
        return None
    parts = time_hint.split(":", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def filter_slots_exact(slots: list[Slot], time_hint: str) -> list[Slot]:
    parsed = parse_time_hint(time_hint)
    if not parsed:
        return slots
    h, mi = parsed
    return [s for s in slots if s.start_at.hour == h and s.start_at.minute == mi]


def filter_slots_by_hour(slots: list[Slot], time_hint: str) -> list[Slot]:
    parsed = parse_time_hint(time_hint)
    if not parsed:
        return slots
    h, _ = parsed
    return [s for s in slots if s.start_at.hour == h]


def nearest_slot_to_time(
    slots: list[Slot],
    target_date: date,
    time_hint: str,
) -> tuple[Slot | None, int]:
    parsed = parse_time_hint(time_hint)
    if not parsed or not slots:
        return None, 0
    h, mi = parsed
    target = datetime.combine(target_date, time(h, mi))
    best: Slot | None = None
    best_delta = 10**9
    for s in slots:
        delta = abs(int((s.start_at - target).total_seconds()))
        if delta < best_delta:
            best_delta = delta
            best = s
    return best, best_delta // 60
