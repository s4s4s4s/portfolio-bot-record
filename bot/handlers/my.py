"""/my — список своих записей и отмена."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import (
    CB_CANCEL_BOOKING,
    main_menu,
    my_bookings_kb,
)
from db.repositories import BookingRepo, ClientRepo
from services.booking_format import fmt_when_display
from services.human_reply import say
from services.persona import booking_cancelled, fmt_booking_card

router = Router(name="my")


@router.message(Command("my"))
async def cmd_my(message: Message, session: AsyncSession) -> None:
    await _show_bookings(message, session)


@router.callback_query(F.data == "menu:my")
async def cb_my(call: CallbackQuery, session: AsyncSession) -> None:
    if isinstance(call.message, Message):
        await _show_bookings(call.message, session, tg_user_id=call.from_user.id if call.from_user else None)
    await call.answer()


async def _show_bookings(
    message: Message, session: AsyncSession, *, tg_user_id: int | None = None,
) -> None:
    user_id = tg_user_id if tg_user_id is not None else (
        message.from_user.id if message.from_user else None
    )
    if user_id is None:
        await message.answer(await say("no_user", {}))
        return
    client = await ClientRepo(session).get_by_tg(user_id)
    if client is None:
        await message.answer(await say("no_bookings_yet", {}), reply_markup=main_menu())
        return
    bookings = await BookingRepo(session).list_active_for_client(client.id)
    if not bookings:
        await message.answer(
            await say("no_active_bookings", {}),
            reply_markup=main_menu(),
        )
        return
    lines: list[str] = []
    kb_items: list[tuple[int, str]] = []
    for b in bookings:
        slot = b.slot
        service = slot.service if slot else None
        master = slot.master if slot else None
        if not slot or not service or not master:
            continue
        when = fmt_when_display(slot.start_at)
        lines.append(fmt_booking_card(service.name, master.name, when))
        kb_items.append((b.id, when))
    await message.answer(
        "\n\n".join(lines) if lines else "Нет активных записей.",
        reply_markup=my_bookings_kb(kb_items, with_exit=True, exit_label="← Меню"),
    )


@router.callback_query(F.data.startswith(CB_CANCEL_BOOKING))
async def cb_cancel_booking(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None or call.from_user is None:
        await call.answer()
        return
    booking_id = int(call.data.removeprefix(CB_CANCEL_BOOKING))
    repo = BookingRepo(session)
    booking = await repo.get(booking_id)
    if booking is None or booking.status != "active":
        await call.answer("Запись не найдена или уже отменена.", show_alert=True)
        return
    client = await ClientRepo(session).get_by_tg(call.from_user.id)
    if client is None or booking.client_id != client.id:
        await call.answer("Это не ваша запись.", show_alert=True)
        return
    await repo.cancel(booking, reason="cancelled by client")
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.answer(await booking_cancelled())
    await call.answer()
