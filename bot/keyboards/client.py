"""Inline-клавиатуры клиента."""
from __future__ import annotations

from datetime import date, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import Master, Service, Slot
from services.persona import cancel_booking_button_label
from services.service_grammar import service_speech_label

_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

CB_BACK = "back"
CB_CANCEL = "cancel"
CB_CONFIRM = "confirm"
CB_EDIT_NAME = "edit:name"
CB_EDIT_PHONE = "edit:phone"

CB_PICK_SERVICE = "svc:"
CB_PICK_MASTER = "mst:"
CB_PICK_DATE = "dt:"
CB_PICK_SLOT = "slt:"
CB_CANCEL_BOOKING = "cnl:"
CB_CANCEL_PICK_ABORT = "cnl:abort"
CB_CANCEL_ALL_YES = "cnlall:yes"
CB_CANCEL_ALL_NO = "cnlall:no"


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться", callback_data="menu:book")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="menu:my")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])


def services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for svc in services:
        rows.append([
            InlineKeyboardButton(
                text=f"{service_speech_label(svc.name)} · {svc.duration_min} мин · {svc.price_kop // 100} ₽",
                callback_data=f"{CB_PICK_SERVICE}{svc.id}",
            ),
        ])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def masters_kb(
    masters: list[Master],
    *,
    button_labels: dict[int, str] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in masters:
        label = (button_labels or {}).get(m.id, m.name)
        rows.append([
            InlineKeyboardButton(text=label, callback_data=f"{CB_PICK_MASTER}{m.id}"),
        ])
    rows.append([
        InlineKeyboardButton(text="Назад", callback_data=CB_BACK),
        InlineKeyboardButton(text="Отмена", callback_data=CB_CANCEL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dates_kb(dates: list[date]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for d in dates:
        wd = _WEEKDAYS[d.weekday()]
        chunk.append(
            InlineKeyboardButton(
                text=f"{d.strftime('%d.%m')} {wd}",
                callback_data=f"{CB_PICK_DATE}{d.isoformat()}",
            ),
        )
        if len(chunk) == 3:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([
        InlineKeyboardButton(text="Назад", callback_data=CB_BACK),
        InlineKeyboardButton(text="Отмена", callback_data=CB_CANCEL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_kb(slots: list[Slot]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for s in slots:
        chunk.append(
            InlineKeyboardButton(
                text=s.start_at.strftime("%H:%M"),
                callback_data=f"{CB_PICK_SLOT}{s.id}",
            ),
        )
        if len(chunk) == 3:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([
        InlineKeyboardButton(text="Назад", callback_data=CB_BACK),
        InlineKeyboardButton(text="Отмена", callback_data=CB_CANCEL),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=CB_CONFIRM)],
        [
            InlineKeyboardButton(text="✏️ Имя", callback_data=CB_EDIT_NAME),
            InlineKeyboardButton(text="✏️ Телефон", callback_data=CB_EDIT_PHONE),
        ],
        [InlineKeyboardButton(text="✖ Отменить", callback_data=CB_CANCEL)],
    ])


def my_bookings_kb(
    items: list[tuple[int, str]],
    *,
    with_exit: bool = False,
    exit_label: str = "Не отменять",
) -> InlineKeyboardMarkup:
    """items: (booking_id, when_label для кнопки)."""
    rows: list[list[InlineKeyboardButton]] = []
    for bid, when_label in items:
        rows.append([
            InlineKeyboardButton(
                text=cancel_booking_button_label(when_label),
                callback_data=f"{CB_CANCEL_BOOKING}{bid}",
            ),
        ])
    if with_exit:
        rows.append([
            InlineKeyboardButton(text=exit_label, callback_data=CB_CANCEL_PICK_ABORT),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else InlineKeyboardMarkup(inline_keyboard=[])


def cancel_all_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отменить все", callback_data=CB_CANCEL_ALL_YES)],
        [InlineKeyboardButton(text="✖ Нет", callback_data=CB_CANCEL_ALL_NO)],
    ])


def fmt_slot_caption(slot: Slot, service: Service, master: Master) -> str:
    """Текст для confirm-карточки."""
    when = slot.start_at.strftime("%d.%m.%Y %H:%M")
    price = service.price_kop // 100
    return (
        f"{service_speech_label(service.name)} · {master.name} · {when}\n"
        f"{service.duration_min} мин · {price} ₽"
    )
