"""Inline-клавиатуры админа."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="admin:today")],
        [InlineKeyboardButton(text="📅 Завтра", callback_data="admin:tomorrow")],
        [InlineKeyboardButton(text="➕ Добавить слот", callback_data="admin:add_slot")],
        [InlineKeyboardButton(text="🚫 Заблокировать слот", callback_data="admin:block_slot")],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
    ])


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bcast:go")],
        [InlineKeyboardButton(text="✖ Отменить", callback_data="bcast:cancel")],
    ])
