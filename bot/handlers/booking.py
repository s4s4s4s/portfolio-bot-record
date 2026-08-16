"""FSM-цепочка бронирования.

Поток (см. SPEC.md §4):
   service → master → date → slot → name → phone → confirm
"""
from __future__ import annotations

from datetime import date as _date

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.booking_helpers import (
    begin_confirm_name_edit,
    begin_confirm_phone_edit,
    continue_after_master_pick,
    handle_contact_step_text,
    refresh_confirm_card,
    resolve_name_input,
    resolve_phone_and_confirm,
    try_returning_client_confirm,
)
from bot.handlers.callback_utils import clear_callback_keyboard, send_via_callback
from bot.keyboards.client import (
    CB_BACK,
    CB_CANCEL,
    CB_CONFIRM,
    CB_EDIT_NAME,
    CB_EDIT_PHONE,
    CB_PICK_DATE,
    CB_PICK_MASTER,
    CB_PICK_SERVICE,
    CB_PICK_SLOT,
    dates_kb,
    main_menu,
    masters_kb,
    services_kb,
    slots_kb,
)
from bot.states import BookingStates
from db.repositories import (
    MasterRepo,
    ServiceRepo,
    SlotRepo,
)
from services.booking_confirm import (
    ConfirmFinalizeResult,
    finalize_booking_confirm,
)
from services.copy_variants import date_step_nudge
from services.human_reply import say
from services.persona import (
    booking_created,
    choose_date_prompt,
    choose_master_prompt,
    choose_slot_prompt,
    name_length_error,
    step_cancelled,
)
from services.salon_time import is_past_date, is_past_slot
from services.service_grammar import service_accusative, service_speech_label

router = Router(name="booking")


# ── Старт сценария ────────────────────────────────────────────────────


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _start_booking(message, state, session)


@router.callback_query(F.data == "menu:book")
async def cb_book_from_menu(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if isinstance(call.message, Message):
        await _start_booking(call.message, state, session)
    await call.answer()


async def _start_booking(message: Message, state: FSMContext, session: AsyncSession) -> None:
    repo = ServiceRepo(session)
    services = await repo.list_active()
    if not services:
        await message.answer(await say("no_services", {}))
        return
    await state.set_state(BookingStates.choosing_service)
    await message.answer(await say("pick_service", {}), reply_markup=services_kb(services))


# ── service → master ──────────────────────────────────────────────────


@router.callback_query(BookingStates.choosing_service, F.data == CB_CANCEL)
async def cb_cancel_at_service(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_text(await step_cancelled(), reply_markup=None)
    await call.answer()


@router.callback_query(BookingStates.choosing_service, F.data.startswith(CB_PICK_SERVICE))
async def cb_pick_service(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None:
        await call.answer()
        return
    service_id = int(call.data.removeprefix(CB_PICK_SERVICE))
    masters = await MasterRepo(session).list_for_service(service_id)
    if not masters:
        service = await ServiceRepo(session).get(service_id)
        svc_name = service.name if service else "услугу"
        from services.service_grammar import no_masters_message_async

        await call.answer(await no_masters_message_async(svc_name), show_alert=True)
        return
    await state.update_data(service_id=service_id)
    if len(masters) == 1:
        master = masters[0]
        slot_repo = SlotRepo(session)
        dates = await slot_repo.list_available_dates(master.id, service_id=service_id, days=14)
        if not dates:
            await call.answer(await say("master_no_slots_14d", {}), show_alert=True)
            return
        service = await ServiceRepo(session).get(service_id)
        price_text = ""
        if service:
            price_text = f"💅 <b>{service_speech_label(service.name)}</b> · {service.duration_min} мин · {service.price_kop // 100} ₽\n\n"
        await state.update_data(master_id=master.id)
        if isinstance(call.message, Message) and await continue_after_master_pick(
            call.message, state, session, service_id=service_id, master_id=master.id,
        ):
            await call.answer()
            return
        await state.set_state(BookingStates.choosing_date)
        if isinstance(call.message, Message):
            await call.message.edit_text(
                f"{price_text}{await choose_date_prompt(master.name)}",
                reply_markup=dates_kb(dates),
            )
        await call.answer()
        return
    await state.set_state(BookingStates.choosing_master)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            await choose_master_prompt(), reply_markup=masters_kb(masters),
        )
    await call.answer()


# ── Back (step back in FSM) ─────────────────────────────────────────────
@router.callback_query(
    StateFilter(
        BookingStates.choosing_master,
        BookingStates.choosing_date,
        BookingStates.choosing_slot,
    ),
    F.data == CB_BACK,
)
async def cb_back_fsm(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    current = await state.get_state()
    data = await state.get_data()
    if current == BookingStates.choosing_slot:
        master_id = data.get("master_id")
        service_id = data.get("service_id")
        if master_id and service_id:
            dates = await SlotRepo(session).list_available_dates(
                int(master_id), service_id=int(service_id), days=14,
            )
            if dates and isinstance(call.message, Message):
                await state.set_state(BookingStates.choosing_date)
                await call.message.edit_text(
                    await date_step_nudge(), reply_markup=dates_kb(dates),
                )
        await call.answer()
        return
    if current == BookingStates.choosing_date:
        service_id = data.get("service_id")
        if service_id:
            masters = await MasterRepo(session).list_for_service(int(service_id))
            if masters and isinstance(call.message, Message):
                await state.set_state(BookingStates.choosing_master)
                await call.message.edit_text(
                    await choose_master_prompt(), reply_markup=masters_kb(masters),
                )
        await call.answer()
        return
    if current == BookingStates.choosing_master:
        services = await ServiceRepo(session).list_active()
        if services and isinstance(call.message, Message):
            await state.set_state(BookingStates.choosing_service)
            await call.message.edit_text(await say("pick_service", {}), reply_markup=services_kb(services))
        await call.answer()
        return
    await call.answer()


# ── Cancel (global step-back) ──────────────────────────────────────────
@router.callback_query(
    StateFilter(BookingStates.choosing_service, BookingStates.choosing_master, BookingStates.choosing_date, BookingStates.choosing_slot),
    F.data == CB_CANCEL,
)
async def cb_cancel_fsm(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_text(await step_cancelled(), reply_markup=None)
        await call.message.answer("👇", reply_markup=main_menu())
    await call.answer()


# ── master → date ─────────────────────────────────────────────────────


@router.callback_query(BookingStates.choosing_master, F.data.startswith(CB_PICK_MASTER))
async def cb_pick_master(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None:
        await call.answer()
        return
    master_id = int(call.data.removeprefix(CB_PICK_MASTER))

    # Validate master can perform the selected service
    data = await state.get_data()
    service_id = data.get("service_id")
    if service_id:
        valid_masters = await MasterRepo(session).list_for_service(service_id)
        if not any(m.id == master_id for m in valid_masters):
            master = await MasterRepo(session).get(master_id)
            service = await ServiceRepo(session).get(service_id)
            master_name = master.name if master else "—"
            service_name = service_accusative(service.name) if service else "—"
            valid_names = ", ".join(m.name for m in valid_masters) if valid_masters else "нет"
            await call.answer(
                await say(
                    "invalid_master_alert",
                    {
                        "master": master_name,
                        "service_acc": service_name,
                        "alternatives": valid_names,
                    },
                ),
                show_alert=True,
            )
            return

    slot_repo = SlotRepo(session)
    data = await state.get_data()
    service_id = data.get("service_id")
    dates = await slot_repo.list_available_dates(master_id, service_id=service_id, days=14)
    if not dates:
        await call.answer(await say("master_no_slots_14d", {}), show_alert=True)
        return
    # Fetch service for price info
    service = await ServiceRepo(session).get(service_id) if service_id else None
    price_text = ""
    if service:
        price_text = f"💅 <b>{service_speech_label(service.name)}</b> · {service.duration_min} мин · {service.price_kop // 100} ₽\n\n"
    master = await MasterRepo(session).get(master_id)
    master_name = master.name if master else "Мастер"
    await state.update_data(master_id=master_id)
    if isinstance(call.message, Message):
        from services.period_offer import try_period_slot_after_master

        if await try_period_slot_after_master(call.message, state, session, master_id):
            await call.answer()
            return
    if isinstance(call.message, Message) and service_id and await continue_after_master_pick(
        call.message, state, session, service_id=int(service_id), master_id=master_id,
    ):
        await call.answer()
        return
    await state.set_state(BookingStates.choosing_date)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            f"{price_text}{await choose_date_prompt(master_name)}",
            reply_markup=dates_kb(dates),
        )
    await call.answer()


# ── date → slot ───────────────────────────────────────────────────────


@router.callback_query(F.data.startswith(CB_PICK_DATE))
async def cb_pick_date(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None:
        await call.answer()
        return
    data = await state.get_data()
    if not data.get("master_id") or not data.get("service_id"):
        await call.answer(
            await say("session_expired", {}),
            show_alert=True,
        )
        await state.clear()
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
        await call.answer(await say("day_no_slots_alert", {}), show_alert=True)
        return
    await state.update_data(target_date=iso_date)
    await state.set_state(BookingStates.choosing_slot)
    master = await MasterRepo(session).get(master_id)
    master_name = master.name if master else "Мастер"
    if isinstance(call.message, Message):
        await call.message.edit_text(
            await choose_slot_prompt(master_name, target.strftime("%d.%m")),
            reply_markup=slots_kb(slots),
        )
    await call.answer()


# ── slot → name ───────────────────────────────────────────────────────


@router.callback_query(F.data.startswith(CB_PICK_SLOT))
async def cb_pick_slot(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if call.data is None:
        await call.answer()
        return
    slot_id = int(call.data.removeprefix(CB_PICK_SLOT))
    slot = await SlotRepo(session).get(slot_id)
    if slot is None or slot.status != "available" or is_past_slot(slot.start_at):
        await call.answer(await say("slot_past", {}), show_alert=True)
        return

    time_label = slot.start_at.strftime("%H:%M")
    await call.answer(f"Время {time_label}")

    await state.update_data(
        slot_id=slot_id,
        service_id=slot.service_id,
        master_id=slot.master_id,
        target_date=slot.start_at.date().isoformat(),
    )
    await clear_callback_keyboard(call)

    if await try_returning_client_confirm(call, state, session, slot_id):
        return

    await state.set_state(BookingStates.entering_name)
    prompt = await say("slot_time_ack", {"time": time_label})
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(prompt, reply_markup=None)
        except Exception:
            await send_via_callback(call, prompt)
    else:
        await send_via_callback(call, prompt)


# ── name → phone ──────────────────────────────────────────────────────


@router.message(BookingStates.entering_name)
async def msg_enter_name(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if await handle_contact_step_text(text, message, state, session, step="name"):
        return
    resolved = await resolve_name_input(text, message, state, session)
    if resolved is None:
        await message.answer(await name_length_error())
        return
    await state.update_data(full_name=resolved)
    data = await state.get_data()
    if data.get("edit_from_confirm") == "name":
        await refresh_confirm_card(message, state, session)
        return
    await state.set_state(BookingStates.entering_phone)
    from services.persona import phone_after_name
    await message.answer(await phone_after_name(first_name=resolved))


# ── phone → confirm ───────────────────────────────────────────────────


@router.message(BookingStates.entering_phone)
async def msg_enter_phone(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if await handle_contact_step_text(text, message, state, session, step="phone"):
        return
    await resolve_phone_and_confirm(text, message, state, session)


# ── confirm → done ────────────────────────────────────────────────────


async def _apply_confirm_result_callback(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    result: ConfirmFinalizeResult,
) -> None:
    if result.outcome == "slot_past":
        await call.answer(await say("slot_past", {}), show_alert=True)
        if isinstance(call.message, Message):
            await call.message.edit_text(
                await say("slot_past", {}),
                reply_markup=None,
            )
        return
    if result.outcome == "slot_taken":
        await call.answer(await say("slot_just_taken", {}), show_alert=True)
        if isinstance(call.message, Message):
            await call.message.edit_text(
                await say("slot_just_taken", {}),
                reply_markup=None,
            )
        return
    if isinstance(call.message, Message):
        await call.message.edit_text(
            f"✅ {await booking_created(result.when_str, result.master_name)}",
            reply_markup=None,
        )
        if result.pending_bookings:
            from bot.handlers.nlu import start_pending_booking_if_any

            await start_pending_booking_if_any(call.message, state, session, result.pending_bookings)
        else:
            await call.message.answer("👇", reply_markup=main_menu())
    await call.answer()


@router.callback_query(BookingStates.confirm, F.data == CB_EDIT_NAME)
async def cb_edit_name_at_confirm(call: CallbackQuery, state: FSMContext) -> None:
    if isinstance(call.message, Message):
        await begin_confirm_name_edit(call.message, state)
    await call.answer()


@router.callback_query(BookingStates.confirm, F.data == CB_EDIT_PHONE)
async def cb_edit_phone_at_confirm(call: CallbackQuery, state: FSMContext) -> None:
    if isinstance(call.message, Message):
        await begin_confirm_phone_edit(call.message, state)
    await call.answer()


@router.callback_query(BookingStates.confirm, F.data == CB_CANCEL)
async def cb_cancel_at_confirm(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_text(await step_cancelled(), reply_markup=None)
    await call.answer()


@router.message(BookingStates.confirm, F.text)
async def msg_confirm_text(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    from bot.handlers.booking_helpers import handle_confirm_text_input

    text = (message.text or "").strip()
    await handle_confirm_text_input(text, message, state, session)


@router.callback_query(BookingStates.confirm, F.data == CB_CONFIRM)
async def cb_confirm(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    user = call.from_user
    if user is None:
        await call.answer()
        return
    result = await finalize_booking_confirm(user, state, session)
    if result is None:
        await call.answer(await say("booking_session_gone", {}), show_alert=True)
        return
    await _apply_confirm_result_callback(call, state, session, result)
