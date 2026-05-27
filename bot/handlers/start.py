"""/start, /help, общее меню клиента."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.cancel_booking import handle_cancel_request
from bot.keyboards.client import main_menu
from services.persona import help_text, start_welcome_message

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await start_welcome_message(), reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(await help_text(), parse_mode="HTML", reply_markup=main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    await handle_cancel_request(
        message, state, session, text=(message.text or "").strip() or "отмена",
    )


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery) -> None:
    if call.message is not None and hasattr(call.message, "answer"):
        await call.message.answer(await help_text(), parse_mode="HTML", reply_markup=main_menu())
    await call.answer()
