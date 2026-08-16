"""Окошка по части дня: «завтра вечером» → выбор мастера без лишних шагов."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Literal

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import masters_kb
from bot.states import BookingStates
from db.models import Master, Service, Slot
from db.repositories import MasterRepo, SlotRepo
from services.llm_client import LLMClient
from services.persona import booking_short_line
from services.salon_time import salon_today

PeriodKind = Literal["morning", "afternoon", "evening"]

_PERIOD_BOUNDS: dict[PeriodKind, tuple[int, int]] = {
    "morning": (8, 12),
    "afternoon": (12, 17),
    "evening": (17, 22),
}

_PERIOD_LABEL: dict[PeriodKind, str] = {
    "morning": "утро",
    "afternoon": "день",
    "evening": "вечер",
}


def extract_time_of_day(text: str) -> PeriodKind | None:
    low = (text or "").lower().replace("ё", "е")
    if re.search(r"\bвечер", low):
        return "evening"
    if re.search(r"\bутр", low):
        return "morning"
    if re.search(r"\bдн[еe]м\b", low):
        return "afternoon"
    return None


def slot_in_period(slot: Slot, period: PeriodKind) -> bool:
    start_h, end_h = _PERIOD_BOUNDS[period]
    hour = slot.start_at.hour
    return start_h <= hour < end_h


def _date_phrase(target: date) -> str:
    today = salon_today()
    if target == today + timedelta(days=1):
        return "завтрашний"
    if target == today:
        return "сегодняшний"
    return target.strftime("%d.%m")


def master_informal_at(name: str) -> str:
    stem = (name or "").strip().split()[0]
    low = stem.lower()
    if low == "анна":
        return "Ани"
    if low.startswith("дмитр"):
        return "Димы"
    if low.endswith("а"):
        return stem[:-1] + "и"
    if low.endswith("я"):
        return stem[:-1] + "и"
    if low.endswith("й"):
        return stem[:-1] + "и"
    return stem


def _window_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "окошко"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "окошка"
    return "окошек"


def _join_offer_parts(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} и {parts[1]}"
    return ", ".join(parts[:-1]) + f" и {parts[-1]}"


def build_period_offer_facts(
    target: date,
    period: PeriodKind,
    offers: list[tuple[Master, Slot]],
) -> dict[str, str]:
    parts = [
        f"у {master_informal_at(m.name)} в {s.start_at.strftime('%H:%M')}"
        for m, s in offers
    ]
    n = len(offers)
    return {
        "date_phrase": _date_phrase(target),
        "period_label": _PERIOD_LABEL[period],
        "count": str(n),
        "windows_word": _window_word(n),
        "offer_list": _join_offer_parts(parts),
    }


async def say_period_master_offer(
    target: date,
    period: PeriodKind,
    offers: list[tuple[Master, Slot]],
    *,
    llm: LLMClient | None = None,
) -> str:
    from services import human_reply

    return await human_reply.say(
        "period_master_offer",
        build_period_offer_facts(target, period, offers),
        llm=llm,
    )


async def collect_period_offers(
    session: AsyncSession,
    *,
    service_id: int,
    target: date,
    period: PeriodKind,
) -> list[tuple[Master, Slot]]:
    slot_repo = SlotRepo(session)
    master_repo = MasterRepo(session)
    offers: list[tuple[Master, Slot]] = []
    for master in await master_repo.list_for_service(service_id):
        slots = await slot_repo.list_available_on_date(master.id, target, service_id)
        evening = [s for s in slots if slot_in_period(s, period)]
        if evening:
            offers.append((master, evening[0]))
    offers.sort(key=lambda item: item[1].start_at)
    return offers


async def try_period_slot_after_master(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master_id: int,
) -> bool:
    data = await state.get_data()
    slot_map = data.get("period_slot_map") or {}
    raw_slot = slot_map.get(str(master_id))
    if raw_slot is None:
        return False
    slot = await SlotRepo(session).get(int(raw_slot))
    if slot is None or slot.status != "available":
        await state.update_data(period_slot_map={})
        return False
    from bot.handlers.nlu import _advance_after_slot_pick

    await state.update_data(master_id=master_id, period_slot_map={})
    await _advance_after_slot_pick(message, state, session, slot)
    return True


async def try_start_period_master_shortcut(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    service: Service,
    target: date,
    period: PeriodKind,
) -> bool:
    offers = await collect_period_offers(
        session, service_id=service.id, target=target, period=period,
    )
    if not offers:
        return False

    masters_for_svc = await MasterRepo(session).list_for_service(service.id)
    price = service.price_kop // 100

    if len(offers) == 1 and len(masters_for_svc) == 1:
        master, slot = offers[0]
        await state.update_data(
            service_id=service.id,
            master_id=master.id,
            target_date=target.isoformat(),
            pending_period=period,
        )
        from bot.handlers.nlu import _advance_after_slot_pick

        await message.answer(booking_short_line(service.name, service.duration_min, price))
        await _advance_after_slot_pick(message, state, session, slot)
        return True

    slot_map = {str(m.id): s.id for m, s in offers}
    await state.update_data(
        service_id=service.id,
        target_date=target.isoformat(),
        period_slot_map=slot_map,
        pending_period=period,
    )
    await state.set_state(BookingStates.choosing_master)
    masters = [m for m, _ in offers]
    await message.answer(booking_short_line(service.name, service.duration_min, price))
    await message.answer(
        await say_period_master_offer(target, period, offers),
        reply_markup=masters_kb(masters),
    )
    return True
