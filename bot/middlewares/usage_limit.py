"""Middleware: дневной лимит входящих действий и блокировка злоупотреблений."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from core.config import get_settings
from db.repositories.user_usage import UserUsageRepo
from services.usage_limit import UsageCheckResult


def _extract_user(event: TelegramObject) -> User | None:
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    return None


async def _send_limit_notice(event: TelegramObject, text: str) -> None:
    if isinstance(event, Message):
        await event.answer(text)
        return
    if isinstance(event, CallbackQuery):
        await event.answer(text[:200], show_alert=True)
        if isinstance(event.message, Message):
            await event.message.answer(text)


class UsageLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        settings = get_settings()
        if not settings.enable_usage_limit:
            return await handler(event, data)

        user = _extract_user(event)
        if user is None:
            return await handler(event, data)

        if user.id in settings.admin_ids:
            return await handler(event, data)

        session = data.get("session")
        if session is None:
            return await handler(event, data)

        repo = UserUsageRepo(session)
        result: UsageCheckResult = await repo.record_incoming(
            user.id,
            limit=settings.daily_msg_limit,
            strikes_before_block=settings.daily_msg_strikes_before_block,
        )

        if not result.allowed:
            if result.user_message:
                await _send_limit_notice(event, result.user_message)
            return None

        return await handler(event, data)
