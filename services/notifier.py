"""Отправка уведомлений клиентам.

Есть тонкая обёртка `Notifier`, чтобы scheduler и broadcast могли работать
с любым транспортом — в тестах подменяем на InMemoryNotifier и проверяем
что вызвано.
"""
from __future__ import annotations

import asyncio
from typing import Protocol


class Notifier(Protocol):
    async def send(self, *, tg_user_id: int, text: str) -> bool: ...


class AiogramNotifier:
    """Отправляет сообщения через aiogram-Bot. Импорт aiogram отложен
    до момента использования, чтобы тесты могли импортировать модуль
    без живого подключения к Telegram.
    """

    def __init__(self, bot: object) -> None:
        self._bot = bot

    async def send(self, *, tg_user_id: int, text: str) -> bool:
        try:
            await self._bot.send_message(chat_id=tg_user_id, text=text)  # type: ignore[attr-defined]
            return True
        except Exception:
            from core.logging import get_logger
            get_logger().exception("notifier.send failed for tg_user_id=%s", tg_user_id)
            return False


class InMemoryNotifier:
    """Тестовый notifier: коллекционирует все отправки в self.sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, *, tg_user_id: int, text: str) -> bool:
        self.sent.append((tg_user_id, text))
        return True


async def broadcast(
    notifier: Notifier, *, recipients: list[int], text: str, rate_per_sec: int = 30,
) -> tuple[int, int]:
    """Рассылает text всем recipients с rate-limit. Возвращает (sent_ok, sent_fail).

    Telegram-лимит: 30 msg/sec в одном диалоге. Между батчами по `rate_per_sec`
    спим 1 сек.
    """
    if not recipients:
        return (0, 0)
    sent_ok = 0
    sent_fail = 0
    for i in range(0, len(recipients), rate_per_sec):
        batch = recipients[i:i + rate_per_sec]
        results = await asyncio.gather(
            *(notifier.send(tg_user_id=tg_id, text=text) for tg_id in batch),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception) or r is False:
                sent_fail += 1
            else:
                sent_ok += 1
        if i + rate_per_sec < len(recipients):
            await asyncio.sleep(1.0)
    return (sent_ok, sent_fail)
