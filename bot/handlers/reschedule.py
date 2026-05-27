"""Перенос активной записи на другой слот."""
from __future__ import annotations

from datetime import date as _date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import (
    CB_PICK_DATE,
    CB_PICK_SLOT,
    dates_kb,
    main_menu,
    slots_kb,
)
from bot.states import RescheduleStates
from db.repositories import BookingRepo, ClientRepo, MasterRepo, ServiceRepo, SlotRepo
from services.booking_format import fmt_when_display
from services.booking_hints import apply_hints, extract_date_time, merge_hints
from services.human_reply import say
from services.persona import choose_date_prompt, choose_slot_prompt, reschedule_done
from services.salon_time import is_past_date, is_past_slot
from services.service_grammar import service_speech_label
from services.slot_matching import filter_slots_exact, nearest_slot_to_time, parse_time_hint

router = Router(name="reschedule")

CB_RESCHEDULE_PICK = "rsc:pick:"


async def start_reschedule(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    client = await ClientRepo(session).get_by_tg(user.id)
    if client is None:
        await message.answer(await say("no_active_bookings", {}), reply_markup=main_menu())
        return
    active = await BookingRepo(session).list_active_for_client(client.id)
    if not active:
        await message.answer(await say("no_active_bookings", {}), reply_markup=main_menu())
        return
    if len(active) > 1:
        items = []
        for b in active:
            slot = b.slot
            if slot is None:
                continue
            items.append((b.id, fmt_when_display(slot.start_at)))
        if not items:
            await message.answer(await say("no_active_bookings", {}), reply_markup=main_menu())
            return
        await state.set_state(RescheduleStates.pick_booking)
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        rows = [
            [InlineKeyboardButton(text=when, callback_data=f"{CB_RESCHEDULE_PICK}{bid}")]
            for bid, when in items
        ]
        await message.answer(
            "Какую запись перенести?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return
    await _begin_reschedule(message, state, session, active[0].id)


async def _begin_reschedule(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    booking_id: int,
) -> None:
    booking = await BookingRepo(session).get(booking_id)
    if booking is None or booking.status != "active" or booking.slot is None:
        await state.clear()
        await message.answer(await say("no_active_bookings", {}), reply_markup=main_menu())
        return
    slot = booking.slot
    service = slot.service
    master = slot.master
    if service is None or master is None:
        await state.clear()
        await message.answer(await say("booking_error", {}), reply_markup=main_menu())
        return
    dates = await SlotRepo(session).list_available_dates(
        master.id, service_id=service.id, days=14,
    )
    if not dates:
        await message.answer(
            await say("no_dates", {"master": master.name}),
            reply_markup=main_menu(),
        )
        await state.clear()
        return
    when = fmt_when_display(slot.start_at)
    await state.set_state(RescheduleStates.choosing_date)
    await state.update_data(
        reschedule_booking_id=booking_id,
        service_id=service.id,
        master_id=master.id,
    )
    intro = (
        f"Перенесём запись: <b>{service_speech_label(service.name)}</b> · "
        f"{master.name} · {when}\n\n"
        f"{await choose_date_prompt(master.name)}"
    )
    await message.answer(intro, parse_mode="HTML", reply_markup=dates_kb(dates))


async def _apply_reschedule(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    new_slot_id: int,
) -> None:
    data = await state.get_data()
    booking_id = int(data["reschedule_booking_id"])
    booking = await BookingRepo(session).get(booking_id)
    if booking is None or booking.status != "active":
        await state.clear()
        await message.answer(await say("no_active_bookings", {}), reply_markup=main_menu())
        return
    new_slot = await SlotRepo(session).get(new_slot_id)
    if new_slot is None or new_slot.status != "available" or is_past_slot(new_slot.start_at):
        await message.answer(await say("slot_past", {}))
        return
    old_slot = await SlotRepo(session).get(booking.slot_id)
    if old_slot:
        old_slot.status = "available"
        old_slot.booking_id = None
    reserved = await SlotRepo(session).reserve_atomic(new_slot_id)
    if reserved is None:
        await message.answer(await say("slot_just_taken", {}), reply_markup=main_menu())
        await state.clear()
        return
    booking.slot_id = new_slot_id
    reserved.booking_id = booking.id
    await session.flush()
    service = new_slot.service
    master = new_slot.master
    when = fmt_when_display(new_slot.start_at)
    await state.clear()
    svc_name = service_speech_label(service.name) if service else "—"
    mst_name = master.name if master else "—"
    await message.answer(
        await reschedule_done(svc_name, mst_name, when),
        reply_markup=main_menu(),
    )


async def handle_reschedule_text(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> bool:
    current = await state.get_state()
    if current not in (
        RescheduleStates.choosing_date.state,
        RescheduleStates.choosing_slot.state,
    ):
        return False
    data = await state.get_data()
    service_id = int(data["service_id"])
    master_id = int(data["master_id"])
    service = await ServiceRepo(session).get(service_id)
    master = await MasterRepo(session).get(master_id)
    if service is None or master is None:
        await state.clear()
        return True
    parsed_date, parsed_time = extract_date_time(text)
    await apply_hints(state, parsed_date, parsed_time)
    data = await state.get_data()
    date_hint, time_hint = merge_hints(data, parsed_date, parsed_time)
    target_date: _date | None = None
    if date_hint:
        try:
            target_date = _date.fromisoformat(date_hint)
        except ValueError:
            target_date = None
    if target_date and is_past_date(target_date):
        await message.answer(await say("day_past", {}))
        return True
    slot_repo = SlotRepo(session)
    if target_date is None and current == RescheduleStates.choosing_slot.state:
        saved = data.get("target_date")
        if saved:
            target_date = _date.fromisoformat(saved)
    if target_date is None:
        await message.answer(await say("date_step_nudge", {}))
        return True
    all_slots = await slot_repo.list_available_on_date(master_id, target_date, service_id)
    await state.update_data(target_date=target_date.isoformat())
    if time_hint and all_slots:
        exact = filter_slots_exact(all_slots, time_hint)
        if len(exact) == 1:
            await _apply_reschedule(message, state, session, exact[0].id)
            return True
        parsed = parse_time_hint(time_hint)
        if parsed and not exact:
            nearest, delta_min = nearest_slot_to_time(all_slots, target_date, time_hint)
            if nearest and 0 < delta_min <= 60:
                await state.set_state(RescheduleStates.choosing_slot)
                off = nearest.start_at.strftime("%H:%M")
                req = f"{parsed[0]:02d}:{parsed[1]:02d}"
                await message.answer(
                    f"На {req} мест нет — ближайшее {off}. Подходит?",
                    reply_markup=slots_kb([nearest]),
                )
                return True
    if all_slots:
        await state.set_state(RescheduleStates.choosing_slot)
        times = [s.start_at.strftime("%H:%M") for s in all_slots]
        await message.answer(
            await choose_slot_prompt(master.name, target_date.strftime("%d.%m"), times=times),
            reply_markup=slots_kb(all_slots),
        )
        return True
    await message.answer(await say("no_slots", {"master": master.name}))
    return True


@router.callback_query(RescheduleStates.pick_booking, F.data.startswith(CB_RESCHEDULE_PICK))
async def cb_reschedule_pick_booking(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None or not isinstance(call.message, Message):
        await call.answer()
        return
    booking_id = int(call.data.removeprefix(CB_RESCHEDULE_PICK))
    await _begin_reschedule(call.message, state, session, booking_id)
    await call.answer()


@router.callback_query(RescheduleStates.choosing_date, F.data.startswith(CB_PICK_DATE))
async def cb_reschedule_date(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None or not isinstance(call.message, Message):
        await call.answer()
        return
    iso_date = call.data.removeprefix(CB_PICK_DATE)
    target = _date.fromisoformat(iso_date)
    if is_past_date(target):
        await call.answer(await say("day_past", {}), show_alert=True)
        return
    data = await state.get_data()
    master_id = int(data["master_id"])
    service_id = int(data["service_id"])
    slots = await SlotRepo(session).list_available_on_date(master_id, target, service_id)
    if not slots:
        await call.answer("На этот день нет окон", show_alert=True)
        return
    master = await MasterRepo(session).get(master_id)
    await state.update_data(target_date=iso_date)
    await state.set_state(RescheduleStates.choosing_slot)
    times = [s.start_at.strftime("%H:%M") for s in slots]
    await call.message.edit_text(
        await choose_slot_prompt(master.name if master else "мастер", target.strftime("%d.%m"), times=times),
        reply_markup=slots_kb(slots),
    )
    await call.answer()


@router.callback_query(RescheduleStates.choosing_slot, F.data.startswith(CB_PICK_SLOT))
async def cb_reschedule_slot(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None or not isinstance(call.message, Message):
        await call.answer()
        return
    slot_id = int(call.data.removeprefix(CB_PICK_SLOT))
    slot = await SlotRepo(session).get(slot_id)
    if slot is None or slot.status != "available" or is_past_slot(slot.start_at):
        await call.answer(await say("slot_past", {}), show_alert=True)
        return
    await call.answer(f"На {slot.start_at.strftime('%H:%M')}")
    await _apply_reschedule(call.message, state, session, slot_id)
