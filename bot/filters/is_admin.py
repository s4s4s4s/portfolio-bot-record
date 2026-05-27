"""Фильтр прав администратора. Использует ADMIN_IDS из Settings."""
from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.config import get_settings


class IsAdmin(Filter):
    """Пропускает только апдейты от пользователей из ADMIN_IDS."""

    async def __call__(self, event: TelegramObject) -> bool:
        admin_ids = set(get_settings().admin_ids)
        if not admin_ids:
            return False
        if isinstance(event, Message) and event.from_user is not None:
            return event.from_user.id in admin_ids
        if isinstance(event, CallbackQuery) and event.from_user is not None:
            return event.from_user.id in admin_ids
        return False
