"""Окно напоминаний в локальном времени салона (TZ)."""
from __future__ import annotations

from datetime import datetime, timedelta

from services.salon_time import is_past_slot


def reminder_window(
    now: datetime,
    *,
    offset_min: int,
    window_min: int,
) -> tuple[datetime, datetime]:
    after = now + timedelta(minutes=offset_min - window_min)
    before = now + timedelta(minutes=offset_min)
    return after, before


def slot_in_reminder_window(
    start_at: datetime,
    now: datetime,
    *,
    offset_min: int,
    window_min: int,
) -> bool:
    if is_past_slot(start_at, now=now):
        return False
    after, before = reminder_window(now, offset_min=offset_min, window_min=window_min)
    return after <= start_at < before


def test_2h_reminder_before_appointment() -> None:
    now = datetime(2026, 5, 27, 16, 5)
    slot = datetime(2026, 5, 27, 18, 0)
    assert slot_in_reminder_window(slot, now, offset_min=120, window_min=15)


def test_2h_reminder_not_after_appointment() -> None:
    now = datetime(2026, 5, 27, 19, 5)
    slot = datetime(2026, 5, 27, 18, 0)
    assert not slot_in_reminder_window(slot, now, offset_min=120, window_min=15)


def test_utc_now_would_false_positive_without_local_tz() -> None:
    """UTC 16:05 vs slot 18:00 local — ложное попадание, если now в UTC."""
    utc_now = datetime(2026, 5, 27, 16, 5)
    slot = datetime(2026, 5, 27, 18, 0)
    after, before = reminder_window(utc_now, offset_min=120, window_min=15)
    assert after <= slot < before  # баг: UTC now матчит прошедшую запись
