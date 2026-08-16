"""Подтверждение записи: текстовые эвристики и общая финализация FSM."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from aiogram.fsm.context import FSMContext
from aiogram.types import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import BookingRepo, ClientRepo, MasterRepo, SlotRepo
from services.booking_format import fmt_when_display
from services.complaint_detect import looks_like_cancel
from services.salon_time import is_past_slot

ConfirmOutcome = Literal["success", "slot_past", "slot_taken"]
ContactEditKind = Literal["name", "phone", "none"]

_NAME_EDIT_MARKERS = (
    "другое имя",
    "имя другое",
    "другой человек",
    "не то имя",
    "не так зовут",
    "не так называ",
    "ошиблась в имени",
    "ошибся в имени",
    "исправить имя",
    "изменить имя",
    "поменять имя",
    "сменить имя",
)

_PHONE_EDIT_MARKERS = (
    "другой номер",
    "номер другой",
    "не тот номер",
    "не тот телефон",
    "исправить номер",
    "исправить телефон",
    "изменить номер",
    "изменить телефон",
    "поменять номер",
    "поменять телефон",
    "сменить номер",
    "сменить телефон",
    "новый номер",
)

_INLINE_NAME_RE = re.compile(
    r"^(?:имя|зовут|называ(?:ю|ть)|меня\s+зовут)\s+(.{2,60})$",
    re.IGNORECASE,
)
_INLINE_NAME_SKIP = frozenset({
    "другое",
    "другой",
    "новое",
    "новый",
    "не",
    "то",
    "так",
    "ошибка",
    "ошибочно",
})


def _inline_name_value(raw: str) -> str | None:
    m = _INLINE_NAME_RE.match(raw.strip())
    if not m:
        return None
    name = m.group(1).strip()
    if len(name) < 2 or len(name) > 60:
        return None
    if name.lower().replace("ё", "е") in _INLINE_NAME_SKIP:
        return None
    return name


@dataclass(slots=True)
class ConfirmFinalizeResult:
    outcome: ConfirmOutcome
    when_str: str = ""
    master_name: str = ""
    pending_bookings: list[dict[str, str]] = field(default_factory=list)


def detect_confirm_contact_edit(text: str) -> tuple[ContactEditKind, str | None]:
    """На шаге confirm: смена имени/телефона; второе значение — готовое имя или +7…"""
    raw = (text or "").strip()
    if not raw:
        return "none", None
    low = raw.lower().replace("ё", "е")

    from services.phone import normalize_phone

    for marker in _PHONE_EDIT_MARKERS:
        if marker in low:
            normalized = normalize_phone(raw)
            if normalized is None:
                for word in raw.split():
                    normalized = normalize_phone(word)
                    if normalized:
                        break
            return "phone", normalized

    for marker in _NAME_EDIT_MARKERS:
        if marker in low:
            return "name", _inline_name_value(raw)

    if any(p in low for p in ("помен", "измен", "смен", "исправ")) and "имя" in low:
        return "name", _inline_name_value(raw)

    if any(p in low for p in ("помен", "измен", "смен", "исправ")) and any(
        w in low for w in ("номер", "телефон", "тел")
    ):
        normalized = normalize_phone(raw)
        return "phone", normalized

    inline_name = _inline_name_value(raw)
    if inline_name:
        return "name", inline_name

    return "none", None


def looks_like_confirm_yes(text: str) -> bool:
    """«да», «всё верно» и короткие синонимы на шаге confirm."""
    if detect_confirm_contact_edit(text)[0] != "none":
        return False
    t = (text or "").strip().lower().replace("ё", "е")
    if not t or looks_like_cancel(t):
        return False
    if t in {
        "да",
        "дпа",
        "даа",
        "ага",
        "угу",
        "yes",
        "ok",
        "ок",
        "okay",
        "подтверждаю",
        "верно",
        "все верно",
        "всё верно",
        "давай",
        "+",
    }:
        return True
    if t.startswith("да ") or t.startswith("да,"):
        return True
    if "верно" in t and len(t) <= 40:
        return True
    return bool(t.startswith("подтверж"))


def looks_like_confirm_no(text: str) -> bool:
    """«нет», «не надо» и короткий отказ на шаге confirm."""
    t = (text or "").strip().lower().replace("ё", "е")
    if not t:
        return False
    if looks_like_cancel(t):
        return True
    if t in {"нет", "не", "неа", "не нужно", "не хочу", "не буду", "не записывай"}:
        return True
    return bool(t.startswith("нет ") or t.startswith("нет,"))


async def finalize_booking_confirm(
    user: User,
    state: FSMContext,
    session: AsyncSession,
) -> ConfirmFinalizeResult | None:
    """Атомарно резервирует слот и создаёт booking. Очищает FSM при любом исходе."""
    data = await state.get_data()
    raw_slot = data.get("slot_id")
    if raw_slot is None:
        return None
    slot_id = int(raw_slot)

    slot_repo = SlotRepo(session)
    booking_repo = BookingRepo(session)
    client_repo = ClientRepo(session)

    slot = await slot_repo.get(slot_id)
    if slot is None or is_past_slot(slot.start_at):
        await state.clear()
        return ConfirmFinalizeResult(outcome="slot_past")
    if slot.status != "available":
        existing = await booking_repo.get_by_slot_id(slot_id)
        client = await client_repo.get_by_tg(user.id)
        if (
            existing is not None
            and existing.status == "active"
            and client is not None
            and existing.client_id == client.id
        ):
            when_str = fmt_when_display(slot.start_at)
            master_name = ""
            if slot.master_id:
                master = await MasterRepo(session).get(slot.master_id)
                if master:
                    master_name = master.name
            pending = list(data.get("pending_bookings") or [])
            await state.clear()
            return ConfirmFinalizeResult(
                outcome="success",
                when_str=when_str,
                master_name=master_name,
                pending_bookings=pending,
            )
        await state.clear()
        return ConfirmFinalizeResult(outcome="slot_taken")

    client = await client_repo.upsert(
        tg_user_id=user.id,
        tg_username=user.username,
        full_name=str(data["full_name"]),
        phone=str(data["phone"]),
    )

    reserved = await slot_repo.reserve_atomic(slot_id)
    if reserved is None:
        await state.clear()
        return ConfirmFinalizeResult(outcome="slot_taken")

    try:
        booking = await booking_repo.create_active_for_slot(
            slot_id=slot_id, client_id=client.id,
        )
    except IntegrityError:
        await session.rollback()
        await state.clear()
        return ConfirmFinalizeResult(outcome="slot_taken")
    reserved.booking_id = booking.id
    await session.flush()

    pending = list(data.get("pending_bookings") or [])
    when_str = fmt_when_display(reserved.start_at)
    master_name = ""
    if reserved.master_id:
        master = await MasterRepo(session).get(reserved.master_id)
        if master:
            master_name = master.name
    await state.clear()
    return ConfirmFinalizeResult(
        outcome="success",
        when_str=when_str,
        master_name=master_name,
        pending_bookings=pending,
    )
