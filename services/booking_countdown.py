"""«Сколько осталось до записи» — обратный отсчёт, не карточка и не новая запись."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import main_menu
from db.repositories import BookingRepo, ClientRepo
from services import human_reply
from services.booking_format import fmt_when_display
from services.copy_variants import master_dative
from services.salon_time import salon_now_naive
from services.service_grammar import service_speech_label

_TIME_UNTIL_RE = re.compile(
    r"(?:"
    r"сколько\s+(?:времени\s+)?(?:ещё|еще\s+)?остал(?:ось|ся)?|"
    r"через\s+сколько\s+(?:до\s+)?(?:запис|визит|приёма|приема)|"
    r"остал(?:ось|ся)\s+до\s+(?:запис|визит|приёма|приема|неё|нее)|"
    r"сколько\s+(?:ещё|еще\s+)?(?:до\s+)?(?:запис|визит)"
    r")",
    re.IGNORECASE,
)


def looks_like_time_until_booking(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if _TIME_UNTIL_RE.search(low):
        return True
    if "не во сколько" in low and "остал" in low:
        return True
    if "сколько времени" in low and any(w in low for w in ("остал", "до запис", "до визит", "до неё", "до нее")):
        return True
    if "я спросил" in low and "остал" in low:
        return True
    return False


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        return many
    if n1 == 1:
        return one
    if 2 <= n1 <= 4:
        return few
    return many


def format_timedelta_ru(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total <= 0:
        return "уже пора — если опаздываете, напишите нам"
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} {_plural(days, 'день', 'дня', 'дней')}")
    if hours:
        parts.append(f"{hours} {_plural(hours, 'час', 'часа', 'часов')}")
    if not days and minutes >= 1:
        parts.append(f"{minutes} {_plural(minutes, 'минута', 'минуты', 'минут')}")
    if not parts:
        return "меньше минуты"
    return " ".join(parts)


def _remaining_until(slot_at: datetime, *, now: datetime | None = None) -> str:
    current = now or salon_now_naive()
    return format_timedelta_ru(slot_at - current)


async def answer_time_until_booking(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        await message.answer(await human_reply.say("no_user", {}))
        return

    client = await ClientRepo(session).get_by_tg(user.id)
    if client is None:
        await message.answer(
            await human_reply.say("booking_countdown_none", {}),
            reply_markup=main_menu(),
        )
        return

    bookings = await BookingRepo(session).list_active_for_client(client.id)
    now = salon_now_naive()
    upcoming = [
        b for b in bookings
        if b.slot is not None and b.slot.start_at >= now
    ]
    upcoming.sort(key=lambda b: b.slot.start_at)  # type: ignore[union-attr]

    if not upcoming:
        await message.answer(
            await human_reply.say("booking_countdown_none", {}),
            reply_markup=main_menu(),
        )
        return

    if len(upcoming) == 1:
        b = upcoming[0]
        slot = b.slot
        assert slot is not None
        service = slot.service
        master = slot.master
        when = fmt_when_display(slot.start_at)
        remaining = _remaining_until(slot.start_at, now=now)
        service_label = service_speech_label(service.name) if service else "запись"
        master_name = master.name if master else ""
        await message.answer(
            await human_reply.say(
                "booking_countdown",
                {
                    "service": service_label,
                    "master": master_name,
                    "master_dative": master_dative(master_name) if master_name else "",
                    "when": when,
                    "remaining": remaining,
                },
                temperature=0.55,
            ),
            reply_markup=main_menu(),
        )
        return

    lines: list[str] = []
    for b in upcoming[:3]:
        slot = b.slot
        if slot is None:
            continue
        service = slot.service
        master = slot.master
        when = fmt_when_display(slot.start_at)
        remaining = _remaining_until(slot.start_at, now=now)
        svc = service_speech_label(service.name) if service else "запись"
        mst = master_dative(master.name) if master else ""
        lines.append(f"{svc} к {mst} ({when}) — ещё {remaining}")

    await message.answer(
        await human_reply.say(
            "booking_countdown_multi",
            {"lines": "\n".join(lines)},
            temperature=0.55,
        ),
        reply_markup=main_menu(),
    )
