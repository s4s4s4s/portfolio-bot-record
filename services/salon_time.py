"""«Сейчас» и «сегодня» в часовом поясе салона (naive datetime, как в слотах)."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from core.config import get_settings


def salon_now_naive() -> datetime:
    tz = ZoneInfo(get_settings().tz)
    return datetime.now(tz).replace(tzinfo=None, microsecond=0)


def salon_today() -> date:
    return salon_now_naive().date()


def is_past_date(target: date) -> bool:
    return target < salon_today()


def is_past_slot(start_at: datetime, *, now: datetime | None = None) -> bool:
    current = (now or salon_now_naive()).replace(microsecond=0)
    return start_at.replace(microsecond=0) < current


def slot_query_from(target_date: date, *, now: datetime | None = None) -> datetime | None:
    """Нижняя граница start_at для выборки слотов на дату; None — день уже прошёл."""
    current = (now or salon_now_naive()).replace(microsecond=0)
    today = current.date()
    if target_date < today:
        return None
    day_start = datetime.combine(target_date, time.min)
    if target_date == today:
        return current
    return day_start
