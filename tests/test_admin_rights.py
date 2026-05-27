"""Тесты прав администратора: фильтр IsAdmin."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User

from bot.filters.is_admin import IsAdmin
from core.config import reload_settings

pytestmark = pytest.mark.asyncio


def _user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="t")


def _msg(user_id: int) -> Message:
    """Лёгкий aiogram Message с from_user."""
    return Message.model_construct(
        message_id=1,
        date=0,  # type: ignore[arg-type]
        chat=MagicMock(),
        from_user=_user(user_id),
        text="x",
    )


def _cb(user_id: int) -> CallbackQuery:
    return CallbackQuery.model_construct(
        id="x",
        from_user=_user(user_id),
        chat_instance="x",
        data="x",
    )


async def test_admin_passes_for_admin_message() -> None:
    reload_settings()
    f = IsAdmin()
    assert await f(_msg(111)) is True


async def test_admin_blocks_non_admin_message() -> None:
    reload_settings()
    f = IsAdmin()
    assert await f(_msg(999)) is False


async def test_admin_passes_for_admin_callback() -> None:
    reload_settings()
    f = IsAdmin()
    assert await f(_cb(222)) is True


async def test_admin_blocks_non_admin_callback() -> None:
    reload_settings()
    f = IsAdmin()
    assert await f(_cb(7777)) is False


async def test_admin_blocks_unknown_event_type() -> None:
    """fail-closed: если пришёл не Message/CallbackQuery — отбрасываем."""
    reload_settings()
    f = IsAdmin()
    weird = MagicMock()
    weird.from_user = None
    assert await f(weird) is False
