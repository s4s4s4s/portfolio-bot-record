"""Извлечение даты/времени из текста и накопление подсказок в FSM."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from aiogram.fsm.context import FSMContext

from services.salon_time import salon_today

_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среду": 2, "среда": 2,
    "четверг": 3, "пятницу": 4, "пятница": 4,
    "субботу": 5, "суббота": 5, "воскресенье": 6, "воскресенья": 6,
}

_WEEKDAY_ABBR = {
    "пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6,
}

_WEEKDAY_INSTRUMENTAL = (
    "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье",
)

_MONTH_NAMES = {
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
}


def _resolve_day_of_month(day: int, today: date) -> date | None:
    y, m = today.year, today.month
    for _ in range(14):
        try:
            candidate = date(y, m, day)
            if candidate >= today:
                return candidate
        except ValueError:
            pass
        m += 1
        if m > 12:
            m = 1
            y += 1
    return None


def extract_date_time(text: str) -> tuple[str, str]:
    """ISO-дата и HH:MM из живой речи."""
    if not text:
        return "", ""
    low = text.lower()
    date_hint = ""
    time_hint = ""
    today = salon_today()

    if "послепослезавтра" in low or "после послезавтра" in low:
        date_hint = (today + timedelta(days=3)).isoformat()
    elif "послезавтра" in low:
        date_hint = (today + timedelta(days=2)).isoformat()
    elif "завтра" in low:
        date_hint = (today + timedelta(days=1)).isoformat()
    elif "сегодня" in low:
        date_hint = today.isoformat()

    if not date_hint:
        for wd_name, wd_num in _WEEKDAYS.items():
            if re.search(rf"\b{re.escape(wd_name)}\b", low):
                delta = (wd_num - today.weekday()) % 7
                if delta == 0:
                    delta = 7
                date_hint = (today + timedelta(days=delta)).isoformat()
                break

    if not date_hint:
        for abbr, wd_num in _WEEKDAY_ABBR.items():
            if re.search(rf"(?:^|[\s,]|(?:в|на)\s+){re.escape(abbr)}(?:\.|[\s,]|$)", low):
                delta = (wd_num - today.weekday()) % 7
                if delta == 0:
                    delta = 7
                date_hint = (today + timedelta(days=delta)).isoformat()
                break

    if not date_hint:
        m = re.search(
            r"(\d{1,2})(?:\-?го)?\s*(числа|число|мая|июня|июля|августа|сентября|октября|ноября|декабря|января|февраля|марта|апреля)",
            low,
        )
        if m and m.group(2):
            day = int(m.group(1))
            month = _MONTH_NAMES.get(m.group(2), today.month)
            try:
                date_hint = date(today.year, month, day).isoformat()
            except ValueError:
                pass

    m = re.search(r"(\d{1,2})[:.\s\-](\d{2})(?!\d)", low)
    if m:
        time_hint = f"{int(m.group(1)):02d}:{m.group(2)}"
    elif re.search(r"(?:^|\s)на\s+\d{1,2}(?![\-\s]?(?:е|го|числ))", low):
        m = re.search(
            r"(?:^|\s)на\s+(\d{1,2})(?![\-\s]?(?:е|го|числ))"
            r"(?:\s*[:.](\d{2}))?(?:\s*(?:час|часа|часов))?(?:\s*(?:утра|дня|вечера))?",
            low,
        )
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            span = low[m.start(): m.end() + 8]
            if ("вечера" in span and hour < 12) or ("дня" in span and 1 <= hour <= 6):
                hour += 12
            time_hint = f"{hour:02d}:{minute:02d}"
    elif re.search(r"(?:^|\s)(?:в|к)\s+\d{1,2}", low):
        m = re.search(
            r"(?:^|\s)(?:в|к)\s+(1[0-9]|2[0-3]|[1-9])(?![\d:.])(?:\s*[:.](\d{2}))?",
            low,
        )
        if m:
            minute = int(m.group(2) or 0)
            time_hint = f"{int(m.group(1)):02d}:{minute:02d}"

    if not time_hint:
        word_times = [
            ("два часа дня", 14), ("два часа", 14), ("три часа дня", 15),
            ("три часа", 15), ("четыре часа", 16), ("пять часов", 17),
        ]
        for word, hour in word_times:
            if word in low:
                time_hint = f"{hour:02d}:00"
                break

    if not date_hint:
        m = re.search(
            r"(?:^|\s)на\s+(\d{1,2})[\-\s]?(?:е|го)(?:\s+числа)?",
            low,
        )
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                resolved = _resolve_day_of_month(day, today)
                if resolved:
                    date_hint = resolved.isoformat()

    if date_hint:
        try:
            if date.fromisoformat(date_hint) < today:
                date_hint = ""
        except ValueError:
            date_hint = ""

    return date_hint, time_hint


def merge_hints(
    data: dict[str, Any],
    date_hint: str = "",
    time_hint: str = "",
) -> tuple[str, str]:
    """Объединить подсказки из сообщения и FSM."""
    d = date_hint or str(data.get("pending_date_hint") or data.get("target_date") or "")
    t = time_hint or str(data.get("pending_time_hint") or "")
    return d, t


async def apply_hints(state: FSMContext, date_hint: str = "", time_hint: str = "") -> None:
    updates: dict[str, str] = {}
    if time_hint:
        updates["pending_time_hint"] = time_hint
    if date_hint:
        updates["pending_date_hint"] = date_hint
    if updates:
        await state.update_data(updates)


async def clear_pending_hints(state: FSMContext) -> None:
    await state.update_data(pending_time_hint="", pending_date_hint="")


def format_date_user_label(target: date) -> str:
    """«завтра», «субботу, 24.05» для сообщений клиенту."""
    today = salon_today()
    if target == today + timedelta(days=1):
        return "завтра"
    if target == today:
        return "сегодня"
    wd = _WEEKDAY_INSTRUMENTAL[target.weekday()]
    return f"{wd}, {target.strftime('%d.%m')}"
