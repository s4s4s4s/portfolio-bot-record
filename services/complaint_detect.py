"""Детект жалоб, отказа от записи и бессмысленного ввода."""
from __future__ import annotations

import re

_GIBBERISH_RE = re.compile(r"^[а-яёa-z0-9\s\-]{4,}$", re.IGNORECASE)
_VOWEL_RE = re.compile(r"[аеёиоуыэюяaeiouy]", re.IGNORECASE)
_WORD_RE = re.compile(r"[а-яёa-z]{3,}", re.IGNORECASE)

_REFUSAL_MARKERS = (
    "не запиш", "никогда", "не приду", "не прийду", "нахуй", "нахер",
    "когда я к вам запиш", "хуй когда", "не буду запис",
)

_CHANGE_MIND_MARKERS = ("передумал", "передумала", "не хочу", "не буду идти", "не приду")

_COMPLAINT_MARKERS = (
    "еблан", "идиот", "тупой", "продать", "продаж", "робот", "бот ",
    "как с человеком", "холодн", "бесит", "разозлил", "отврат",
)

_CANCEL_MARKERS = ("отмен", "стоп", "не надо", "забудь про номер", "забудь номер")

_OFF_TOPIC_VULGAR_RE = re.compile(
    r"\b(?:"
    r"сос(?:ал|ала|ать|и|ё|e|at)?|"
    r"хуй|хуя|хуе|пизд|еба|ёб|ебл|бля|"
    r"сука|дебил|идиот|"
    r"пошл(?:и|ёл|ел)|"
    r"ты\s+(?:бот|робот|туп)"
    r")\b",
    re.IGNORECASE,
)

_SALON_TOPIC_RE = re.compile(
    r"запис|услуг|мастер|маник|массаж|стриж|салон|цен|стоим|"
    r"свобод|окн|время|когда|завтра|сегодня|отмен|мои\s+запис",
    re.IGNORECASE,
)


def looks_like_change_mind(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _CHANGE_MIND_MARKERS)


def looks_like_cancel(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _CANCEL_MARKERS)


def looks_like_booking_refusal(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def looks_like_complaint(text: str) -> bool:
    low = text.lower()
    if looks_like_booking_refusal(low):
        return True
    return any(m in low for m in _COMPLAINT_MARKERS)


def looks_like_gibberish(text: str, *, known_tokens: list[str] | None = None) -> bool:
    """Каша букв без осмысленных слов и без совпадения с каталогом."""
    raw = (text or "").strip()
    if len(raw) < 4:
        return False
    low = raw.lower()
    if looks_like_cancel(low) or looks_like_complaint(low):
        return False
    for token in known_tokens or []:
        if token and token.lower() in low:
            return False
    words = _WORD_RE.findall(low)
    if len(words) >= 2:
        return False
    cleaned = re.sub(r"[\s\d\-.,!?]+", "", low)
    if len(cleaned) < 4:
        return False
    if not _GIBBERISH_RE.match(low):
        return False
    if len(words) == 1:
        w = words[0]
        if len(w) >= 9 and len(set(w)) <= 5:
            return True
        if 4 <= len(w) < 9:
            return False
    vowels = len(_VOWEL_RE.findall(cleaned))
    if vowels == 0:
        return True
    if vowels / max(len(cleaned), 1) < 0.15 and len(cleaned) >= 6:
        return True
    if len(set(cleaned)) <= 5 and len(cleaned) >= 8:
        return True
    return len(words) == 0 and len(cleaned) >= 8


def looks_like_same_name(text: str) -> bool:
    low = text.lower().strip()
    return low in ("так же", "как в прошлый раз", "как раньше", "то же", "то же самое")


def looks_like_phone_update(text: str) -> bool:
    low = text.lower()
    return any(
        p in low for p in ("поменяй телефон", "новый номер", "мой номер", "смени номер", "измени номер")
    )


def looks_like_off_topic(text: str) -> bool:
    """Провокация, пошлость или реплика явно не про запись."""
    from services.booking_cancel import looks_like_my_bookings

    raw = (text or "").strip()
    if len(raw) < 2:
        return False
    low = raw.lower()
    if _OFF_TOPIC_VULGAR_RE.search(low):
        return True
    if looks_like_cancel(low) or looks_like_my_bookings(low):
        return False
    if _SALON_TOPIC_RE.search(low):
        return False
    if looks_like_gibberish(raw):
        return False
    if len(raw) <= 24 and not _SALON_TOPIC_RE.search(low):
        words = _WORD_RE.findall(low)
        if len(words) <= 2 and "?" in raw and not any(
            w in low for w in ("привет", "здрав", "спасиб", "пока", "салам")
        ):
            return True
    return False


def looks_like_change_master(text: str) -> bool:
    low = text.lower()
    return (
        any(p in low for p in ("не на ", "а на ", "перенеси", "поменяй", "смени"))
        and any(p in low for p in ("мастер", "анастас", "милен", "дмитри", "анн"))
    ) or ("поменяй" in low and "на " in low)
