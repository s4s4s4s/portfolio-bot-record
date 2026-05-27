"""Краткие названия услуг и винительный падеж для фраз «на …»."""
from __future__ import annotations

_ACCUSATIVE: dict[str, str] = {
    "маникюр": "маникюр",
    "массаж": "массаж",
    "педикюр": "педикюр",
    "стрижка": "стрижку",
    "окрашивание": "окрашивание",
    "мелирование": "мелирование",
    "френч": "френч",
    "шугаринг": "шугаринг",
    "депиляция": "депиляцию",
}


def service_speech_label(name: str) -> str:
    """Имя для речи: без уточнений в скобках."""
    return name.split("(")[0].strip()


def service_accusative(name: str) -> str:
    """Винительный для «на стрижку», «на маникюр» — только основное слово."""
    stem = service_speech_label(name)
    low = stem.lower()
    if low in _ACCUSATIVE:
        return _ACCUSATIVE[low]
    if low.endswith("ка"):
        return low[:-2] + "ку"
    if low.endswith("ия"):
        return low[:-1] + "ю"
    if low.endswith("а"):
        return low[:-1] + "у"
    if low.endswith("я"):
        return low[:-1] + "ю"
    return low


def no_masters_message(service_name: str) -> str:
    """Синхронная обёртка для обратной совместимости — предпочитайте async версию."""
    from services.human_reply import _example_fallback

    acc = service_accusative(service_name)
    return _example_fallback("no_masters_for_service", {"service_acc": acc})


async def no_masters_message_async(service_name: str) -> str:
    from services import human_reply

    return await human_reply.say(
        "no_masters_for_service",
        {"service_acc": service_accusative(service_name)},
    )


def join_service_accusatives(options: list[str]) -> str:
    """«На маникюр, на массаж или на стрижку»."""
    acc = [service_accusative(o) for o in options]
    if not acc:
        return ""
    if len(acc) == 1:
        return f"На {acc[0]}"
    if len(acc) == 2:
        return f"На {acc[0]} или на {acc[1]}"
    return "На " + ", на ".join(acc[:-1]) + f" или на {acc[-1]}"
