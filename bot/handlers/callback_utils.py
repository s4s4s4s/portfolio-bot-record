"""Помощники для callback: ответ даже если FSM сброшен или message недоступен."""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


async def callback_chat_id(call: CallbackQuery) -> int | None:
    if call.message is not None and isinstance(call.message, Message):
        return call.message.chat.id
    if call.from_user is not None:
        return call.from_user.id
    return None


async def clear_callback_keyboard(call: CallbackQuery) -> None:
    if call.message is None or not isinstance(call.message, Message):
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


async def send_via_callback(
    call: CallbackQuery,
    text: str,
    *,
    reply_markup=None,
    prefer_edit: bool = False,
) -> None:
    bot: Bot = call.bot
    chat_id = await callback_chat_id(call)
    if chat_id is None:
        return
    if prefer_edit and call.message is not None and isinstance(call.message, Message):
        try:
            await call.message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
    await bot.send_message(chat_id, text, reply_markup=reply_markup)
