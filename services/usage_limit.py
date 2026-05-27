"""Дневной лимит сообщений и блокировка после N нарушений."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import Settings, get_settings
from db.models import UserUsage


@dataclass(frozen=True)
class UsageCheckResult:
    allowed: bool
    user_message: str | None = None


def today_key(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    tz = ZoneInfo(s.tz)
    return datetime.now(tz).strftime("%Y-%m-%d")


def blocked_user_message(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    contact = (s.salon_admin_contact or "").strip()
    tail = f"\n\nКонтакт администратора: {contact}" if contact else ""
    return (
        "Аккаунт временно ограничен: превышен лимит сообщений несколько раз."
        f"{tail}\n\nДля разблокировки напишите администратору салона."
    )


def limit_exceeded_message(*, strike_count: int, strikes_max: int, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (
        f"Лимит — не больше {s.daily_msg_limit} сообщений в день. "
        f"Сегодня лимит исчерпан. Завтра счётчик обновится.\n"
        f"Нарушение {strike_count} из {strikes_max}."
    )


def check_and_increment(
    usage: UserUsage,
    *,
    today: str,
    limit: int,
    strikes_before_block: int,
    settings: Settings | None = None,
) -> UsageCheckResult:
    """Обновляет счётчики на usage (in-memory) и возвращает, можно ли обрабатывать апдейт."""
    if usage.day_key != today:
        usage.day_key = today
        usage.msg_count = 0

    if usage.blocked:
        return UsageCheckResult(allowed=False, user_message=blocked_user_message(settings))

    usage.msg_count += 1

    if usage.msg_count <= limit:
        return UsageCheckResult(allowed=True)

    # Превышение лимита
    if usage.last_violation_day != today:
        usage.strike_count += 1
        usage.last_violation_day = today
        if usage.strike_count >= strikes_before_block:
            usage.blocked = True
            usage.blocked_at = datetime.utcnow()
            return UsageCheckResult(allowed=False, user_message=blocked_user_message(settings))

    return UsageCheckResult(
        allowed=False,
        user_message=limit_exceeded_message(
            strike_count=usage.strike_count,
            strikes_max=strikes_before_block,
            settings=settings,
        ),
    )
