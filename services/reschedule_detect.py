"""Детект запроса переноса записи."""
from __future__ import annotations


def looks_like_reschedule(text: str) -> bool:
    low = (text or "").lower().replace("ё", "е")
    if not low:
        return False
    move_markers = ("перенес", "перенести", "перенос", "сдвин", "передвин", "перенеси")
    if not any(m in low for m in move_markers):
        return False
    booking_markers = ("запис", "прием", "приём", "визит", "окон", "время", "слот", "мою", "моя", "мои", "наш")
    if any(m in low for m in booking_markers):
        return True
    # «перенеси» / «перенести» без объекта — тоже перенос своей записи
    return any(m in low for m in ("перенеси", "перенести"))

