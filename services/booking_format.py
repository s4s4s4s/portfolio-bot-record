"""Форматирование карточек записи для клиента."""
from __future__ import annotations

import re
from datetime import datetime

_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def fmt_when_display(dt: datetime) -> str:
    """27.05 Ср 18:00 — без года, с днём недели."""
    wd = _WEEKDAYS[dt.weekday()]
    return f"{dt.strftime('%d.%m')} {wd} {dt.strftime('%H:%M')}"


def time_from_when_label(when_label: str) -> str:
    for part in reversed(when_label.split()):
        if re.fullmatch(r"\d{1,2}:\d{2}", part):
            return part
    return ""


from services.service_grammar import service_speech_label


def _speech_service(name: str) -> str:
    return service_speech_label(name)


def _service_emoji(service_name: str) -> str:
    low = service_speech_label(service_name).lower()
    if "массаж" in low:
        return "💆"
    if "стриж" in low:
        return "✂️"
    return "💅"


def format_booking_details(
    service_name: str,
    master_name: str,
    when: str,
    duration_min: int,
    price_rub: int,
    *,
    full_name: str = "",
    phone: str = "",
    include_client: bool = False,
) -> str:
    """Вертикальная карточка: услуга, мастер, дата/время отдельно."""
    label = _speech_service(service_name)
    emoji = _service_emoji(service_name)
    lines = [
        f"{emoji} {label}",
        f"Мастер: {master_name}",
        when,
        f"{duration_min} мин · {price_rub} ₽",
    ]
    if include_client and (full_name or phone):
        lines.append("")
        if full_name:
            lines.append(full_name)
        if phone:
            lines.append(_format_phone_display(phone))
    return "\n".join(lines)


def _format_phone_display(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("7"):
        d = digits[1:]
        return f"+7 {d[:3]} {d[3:6]}-{d[6:8]}-{d[8:10]}"
    return phone


def fmt_confirm_body(
    service_name: str,
    master_name: str,
    when: str,
    duration_min: int,
    price_rub: int,
    full_name: str,
    phone: str,
) -> str:
    return format_booking_details(
        service_name,
        master_name,
        when,
        duration_min,
        price_rub,
        full_name=full_name,
        phone=phone,
        include_client=True,
    )


def fmt_booking_summary(
    service_name: str,
    master_name: str,
    when: str,
    duration_min: int = 0,
    price_rub: int = 0,
) -> str:
    if duration_min and price_rub:
        return format_booking_details(
            service_name, master_name, when, duration_min, price_rub,
        )
    emoji = _service_emoji(service_name)
    label = _speech_service(service_name)
    return f"{emoji} {label}\nМастер: {master_name}\n{when}"


def fmt_booking_card(service_name: str, master_name: str, when: str) -> str:
    return fmt_booking_summary(service_name, master_name, when)
