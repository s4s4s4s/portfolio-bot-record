"""Отмена готовых записей по тексту и /cancel."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import (
    CB_CANCEL_ALL_NO,
    CB_CANCEL_ALL_YES,
    CB_CANCEL_PICK_ABORT,
    cancel_all_confirm_kb,
    main_menu,
    my_bookings_kb,
)
from bot.states import BookingStates, CancelStates
from db.repositories import BookingRepo, ClientRepo
from services.booking_cancel import (
    ActiveBookingView,
    booking_views_from_models,
    looks_like_abort_cancel_pick,
    looks_like_cancel_all_confirm,
    resolve_cancel_pick,
    resolve_cancel_target,
    should_cancel_existing_booking,
)
from services.human_reply import say
from services.persona import (
    booking_cancelled_detail,
    cancel_all_confirm_prompt,
    cancel_all_done,
    cancel_booking_not_found_hint,
    cancel_which_booking_prompt,
    fmt_booking_card,
    leave_bookings_message,
    step_cancelled,
)

router = Router(name="cancel_booking")

_BOOKING_FSM_STATES = frozenset({
    BookingStates.choosing_service.state,
    BookingStates.choosing_master.state,
    BookingStates.choosing_date.state,
    BookingStates.choosing_slot.state,
    BookingStates.entering_name.state,
    BookingStates.entering_phone.state,
    BookingStates.confirm.state,
})


async def _load_client_views(
    session: AsyncSession, tg_user_id: int,
) -> tuple[int | None, list[ActiveBookingView]]:
    client = await ClientRepo(session).get_by_tg(tg_user_id)
    if client is None:
        return None, []
    bookings = await BookingRepo(session).list_active_for_client(client.id)
    return client.id, booking_views_from_models(bookings)


async def _abort_cancel_pick(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await leave_bookings_message(), reply_markup=main_menu())


async def _cancel_one(
    session: AsyncSession,
    *,
    client_id: int,
    booking_id: int,
) -> bool:
    repo = BookingRepo(session)
    booking = await repo.get(booking_id)
    if booking is None or booking.status != "active" or booking.client_id != client_id:
        return False
    await repo.cancel(booking, reason="cancelled by client")
    return True


async def _cancel_all(
    session: AsyncSession,
    *,
    client_id: int,
    views: list[ActiveBookingView],
) -> int:
    cancelled = 0
    for view in views:
        if await _cancel_one(session, client_id=client_id, booking_id=view.booking_id):
            cancelled += 1
    return cancelled


async def _apply_cancel_one(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    client_id: int,
    view: ActiveBookingView,
) -> None:
    ok = await _cancel_one(session, client_id=client_id, booking_id=view.booking_id)
    await state.clear()
    if ok:
        await _reply_cancelled(message, view)
    else:
        await message.answer(
            await say("cancel_already_gone", {}),
            reply_markup=main_menu(),
        )


async def _apply_cancel_pick_result(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    client_id: int,
    views: list[ActiveBookingView],
    resolved,
) -> None:
    if resolved.kind == "one" and resolved.booking_id is not None:
        view = next((v for v in views if v.booking_id == resolved.booking_id), None)
        if view is None:
            await state.clear()
            await message.answer(await step_cancelled(), reply_markup=main_menu())
            return
        await _apply_cancel_one(message, state, session, client_id=client_id, view=view)
        return

    if resolved.kind == "ask":
        ask_views = list(resolved.views) if resolved.views else views
        await _reply_ask_which(message, state, ask_views)
        return

    if resolved.kind == "not_found":
        await _reply_ask_which(message, state, views)
        return

    await state.clear()
    await message.answer(await step_cancelled(), reply_markup=main_menu())


async def _reply_cancelled(message: Message, view: ActiveBookingView) -> None:
    await message.answer(
        await booking_cancelled_detail(view.service_name, view.master_name, view.when_label),
        reply_markup=main_menu(),
    )


async def _enter_pick_cancel_flow(
    message: Message,
    state: FSMContext,
    views: list[ActiveBookingView],
) -> None:
    await state.set_state(CancelStates.pick_booking)
    await state.update_data(pending_cancel_pick=[v.booking_id for v in views])


async def _reply_ask_which(message: Message, state: FSMContext, views: list[ActiveBookingView]) -> None:
    lines = [
        fmt_booking_card(v.service_name, v.master_name, v.when_label)
        for v in views
    ]
    kb_items = [(v.booking_id, v.when_label) for v in views]
    await _enter_pick_cancel_flow(message, state, views)
    await message.answer(
        f"{await cancel_which_booking_prompt()}\n\n" + "\n\n".join(lines),
        reply_markup=my_bookings_kb(kb_items, with_exit=True),
    )


async def _reply_confirm_cancel_all(
    message: Message,
    state: FSMContext,
    views: list[ActiveBookingView],
) -> None:
    lines = [
        fmt_booking_card(v.service_name, v.master_name, v.when_label)
        for v in views
    ]
    await state.set_state(CancelStates.confirm_cancel_all)
    await state.update_data(
        pending_cancel_all=[v.booking_id for v in views],
    )
    await message.answer(
        f"{await cancel_all_confirm_prompt(len(views))}\n\n" + "\n\n".join(lines),
        reply_markup=cancel_all_confirm_kb(),
    )


async def handle_cancel_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    text: str,
) -> None:
    user = message.from_user
    if user is None:
        return

    current_state = await state.get_state()
    was_in_fsm = current_state in _BOOKING_FSM_STATES

    client_id, views = await _load_client_views(session, user.id)

    from services.booking_cancel import _has_cancel_word
    from services.complaint_detect import looks_like_change_mind

    explicit_cancel = _has_cancel_word(text) or looks_like_change_mind(text)

    if not views and not explicit_cancel:
        from bot.handlers.nlu import _handle_user_text

        await _handle_user_text(text, message, state, session)
        return

    if current_state == CancelStates.confirm_cancel_all.state:
        if looks_like_cancel_all_confirm(text):
            data = await state.get_data()
            ids = [int(x) for x in (data.get("pending_cancel_all") or [])]
            pending = [v for v in views if v.booking_id in ids]
            await state.clear()
            if client_id is None or not pending:
                await message.answer(await step_cancelled(), reply_markup=main_menu())
                return
            count = await _cancel_all(session, client_id=client_id, views=pending)
            await message.answer(await cancel_all_done(count), reply_markup=main_menu())
            return
        if any(w in text.lower() for w in ("нет", "не надо", "оставь", "стоп")):
            await _abort_cancel_pick(message, state)
            return
        await message.answer(
            await say("confirm_cancel_all_nudge", {}),
            reply_markup=cancel_all_confirm_kb(),
        )
        return

    await state.clear()

    if client_id is None or not views:
        await message.answer(await step_cancelled(), reply_markup=main_menu())
        return

    if not should_cancel_existing_booking(
        text, was_in_booking_fsm=was_in_fsm, views=views,
    ):
        await state.clear()
        from bot.handlers.nlu import _handle_user_text

        await _handle_user_text(text, message, state, session)
        return

    resolved = resolve_cancel_target(text, views)
    if resolved.kind == "confirm_all":
        confirm_views = list(resolved.views) if resolved.views else views
        await _reply_confirm_cancel_all(message, state, confirm_views)
        return

    if resolved.kind == "one" and resolved.booking_id is not None:
        view = next((v for v in views if v.booking_id == resolved.booking_id), None)
        if view is None:
            await message.answer(await step_cancelled(), reply_markup=main_menu())
            return
        await _apply_cancel_one(message, state, session, client_id=client_id, view=view)
        return

    if resolved.kind == "ask":
        ask_views = list(resolved.views) if resolved.views else views
        await _reply_ask_which(message, state, ask_views)
        return

    if resolved.kind == "not_found":
        await _reply_ask_which(message, state, views)
        return

    await message.answer(await step_cancelled(), reply_markup=main_menu())


async def handle_cancel_pick(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    text: str,
) -> None:
    user = message.from_user
    if user is None:
        return

    if looks_like_abort_cancel_pick(text):
        await _abort_cancel_pick(message, state)
        return

    from db.repositories import ServiceRepo
    from services.booking_cancel import looks_like_service_booking_escape

    services = await ServiceRepo(session).list_active()
    svc_names = [s.name for s in services]
    if looks_like_service_booking_escape(text, svc_names):
        await state.clear()
        from bot.handlers.nlu import _handle_user_text

        await _handle_user_text(text, message, state, session)
        return

    client_id, views = await _load_client_views(session, user.id)
    if client_id is None or not views:
        await state.clear()
        await message.answer(await step_cancelled(), reply_markup=main_menu())
        return

    data = await state.get_data()
    ids = [int(x) for x in (data.get("pending_cancel_pick") or [])]
    pending = [v for v in views if v.booking_id in ids] if ids else views
    if not pending:
        pending = views

    resolved = resolve_cancel_pick(text, pending)
    await _apply_cancel_pick_result(
        message, state, session, client_id=client_id, views=pending, resolved=resolved,
    )


@router.callback_query(F.data == CB_CANCEL_PICK_ABORT)
async def cb_abort_cancel_pick(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(await leave_bookings_message(), reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == CB_CANCEL_ALL_YES)
async def cb_cancel_all_yes(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    user = call.from_user
    if user is None:
        await call.answer()
        return
    client_id, views = await _load_client_views(session, user.id)
    data = await state.get_data()
    ids = [int(x) for x in (data.get("pending_cancel_all") or [])]
    pending = [v for v in views if v.booking_id in ids]
    await state.clear()
    if client_id is None or not pending:
        await call.answer(await say("bookings_already_cancelled_alert", {}), show_alert=True)
        return
    count = await _cancel_all(session, client_id=client_id, views=pending)
    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(await cancel_all_done(count), reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == CB_CANCEL_ALL_NO)
async def cb_cancel_all_no(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(await leave_bookings_message(), reply_markup=main_menu())
    await call.answer()


@router.message(StateFilter(CancelStates.pick_booking), F.text)
async def msg_cancel_pick_text(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    await handle_cancel_pick(message, state, session, text=text)


@router.message(StateFilter(CancelStates.confirm_cancel_all), F.text)
async def msg_cancel_all_confirm_text(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    await handle_cancel_request(message, state, session, text=text)
