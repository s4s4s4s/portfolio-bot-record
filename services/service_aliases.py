"""Синонимы услуг: разговорные названия → каноническое имя в БД."""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_ALIASES: dict[str, str] = {
    "френч": "маникюр",
    "френч-маникюр": "маникюр",
    "френч маникюр": "маникюр",
    "наращивание": "маникюр",
    "педикюр": "маникюр",
    "гель-лак": "маникюр",
    "гель лак": "маникюр",
    "стрижку": "стрижка",
    "подстричь": "стрижка",
    "массажик": "массаж",
}

# Салонные услуги вне каталога — без кавычек в ответе
BEAUTY_UNSUPPORTED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("мелирован", "мелирование"),
    ("мелирова", "мелирование"),
    ("окрашив", "окрашивание"),
    ("балаяж", "балаяж"),
    ("блондирован", "блондирование"),
    ("тонирован", "тонирование"),
    ("колорирован", "колорирование"),
    ("фарбирован", "окрашивание"),
    ("highlight", "мелирование"),
)

# Чужие / нестандартные формулировки — с кавычками
QUOTED_UNSUPPORTED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("золотой дождь", "золотой дождь"),
    ("золотого дождя", "золотой дождь"),
)

UNSUPPORTED_SERVICE_PATTERNS = BEAUTY_UNSUPPORTED_PATTERNS + QUOTED_UNSUPPORTED_PATTERNS


@dataclass(frozen=True)
class UnsupportedServiceMatch:
    label: str
    quoted: bool


def normalize_service_hint(hint: str) -> str:
    """Приводит подсказку к каноническому имени для fuzzy-match."""
    if not hint:
        return hint
    low = hint.lower().strip()
    if low in DEFAULT_ALIASES:
        return DEFAULT_ALIASES[low]
    for alias, canonical in DEFAULT_ALIASES.items():
        if alias in low:
            return canonical
    return hint


def detect_unsupported_service(text: str, entity_hint: str = "") -> UnsupportedServiceMatch | None:
    """Возвращает match с флагом кавычек или None."""
    blob = f"{text} {entity_hint}".lower()
    for pattern, label in BEAUTY_UNSUPPORTED_PATTERNS:
        if pattern in blob:
            return UnsupportedServiceMatch(label=label, quoted=False)
    for pattern, label in QUOTED_UNSUPPORTED_PATTERNS:
        if pattern in blob:
            return UnsupportedServiceMatch(label=label, quoted=True)
    return None


def detect_unsupported_service_label(text: str, entity_hint: str = "") -> str | None:
    """Обратная совместимость: только название услуги."""
    m = detect_unsupported_service(text, entity_hint)
    return m.label if m else None
