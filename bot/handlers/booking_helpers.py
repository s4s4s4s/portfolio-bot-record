"""Общие шаги FSM записи: confirm, контакт, слот."""

from __future__ import annotations

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import confirm_kb, dates_kb, main_menu, masters_kb
from bot.states import BookingStates
from db.repositories import ClientRepo, MasterRepo, ServiceRepo, SlotRepo
from services.booking_format import fmt_when_display
from services.booking_hints import merge_hints
from services.complaint_detect import (
    looks_like_cancel,
    looks_like_gibberish,
    looks_like_same_name,
)
from services.human_reply import say
from services.master_matching import find_master_in_text
from services.period_offer import try_period_slot_after_master
from services.persona import (
    choose_date_prompt,
    choose_master_prompt,
    confirm_intro,
    faq_answer,
    fmt_confirm_body,
    name_prompt,
    phone_after_name,
    phone_invalid_error,
    phone_not_now_hint,
    step_cancelled,
)
from services.phone import normalize_phone
from services.salon_time import is_past_slot
from services.service_grammar import service_speech_label


async def continue_after_master_pick(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    service_id: int,
    master_id: int,
) -> bool:
    """Если клиент уже назвал дату/время — не показывать выбор даты заново."""
    await state.update_data(service_id=service_id, master_id=master_id)
    data = await state.get_data()
    date_hint, time_hint = merge_hints(data, "", "")
    if not date_hint and not time_hint:
        return False

    service = await ServiceRepo(session).get(service_id)
    master = await MasterRepo(session).get(master_id)
    if service is None or master is None:
        return False

    from bot.handlers.nlu import _show_availability
    from services.llm_client import get_llm_client

    await _show_availability(
        message,
        state,
        session,
        service,
        master,
        date_hint,
        time_hint,
        get_llm_client(),
    )
    return True





async def _send_booking_reply(

    *,

    bot: Bot,

    chat_id: int,

    text: str,

    reply_markup: InlineKeyboardMarkup | None = None,

    message: Message | None = None,

) -> None:

    if message is not None:

        await message.answer(text, reply_markup=reply_markup)

    else:

        await bot.send_message(chat_id, text, reply_markup=reply_markup)





async def advance_to_confirm(

    state: FSMContext,

    session: AsyncSession,

    *,

    slot_id: int,

    full_name: str,

    phone: str,

    bot: Bot,

    chat_id: int,

    message: Message | None = None,

) -> bool:

    slot = await SlotRepo(session).get(slot_id)

    if slot is None or slot.status != "available" or is_past_slot(slot.start_at):

        await state.clear()

        text = await say("slot_past", {})

        await _send_booking_reply(

            bot=bot,

            chat_id=chat_id,

            message=message,

            text=text,

            reply_markup=main_menu(),

        )

        return False

    service = await ServiceRepo(session).get(slot.service_id)

    master = await MasterRepo(session).get(slot.master_id)

    if service is None or master is None:

        await state.clear()

        text = await say("booking_error", {})

        await _send_booking_reply(

            bot=bot,

            chat_id=chat_id,

            message=message,

            text=text,

            reply_markup=main_menu(),

        )

        return False

    await state.update_data(

        slot_id=slot_id,

        full_name=full_name,

        phone=phone,

        service_id=service.id,

        master_id=master.id,

        edit_from_confirm=None,

        phone_attempts=0,

    )

    await state.set_state(BookingStates.confirm)

    when = fmt_when_display(slot.start_at)

    body = fmt_confirm_body(

        service.name,

        master.name,

        when,

        service.duration_min,

        service.price_kop // 100,

        full_name,

        phone,

    )

    intro = await confirm_intro()

    await _send_booking_reply(

        bot=bot,

        chat_id=chat_id,

        message=message,

        text=f"{intro}\n\n{body}",

        reply_markup=confirm_kb(),

    )

    return True





async def try_returning_client_confirm(

    event: Message | CallbackQuery,

    state: FSMContext,

    session: AsyncSession,

    slot_id: int,

) -> bool:

    user: User | None
    if isinstance(event, CallbackQuery):

        user = event.from_user

        bot = event.bot

        message = event.message if isinstance(event.message, Message) else None

        chat_id = message.chat.id if message is not None else (user.id if user else None)

    else:

        user = event.from_user

        bot = event.bot

        message = event

        chat_id = event.chat.id

    if user is None or chat_id is None or bot is None:

        return False

    client = await ClientRepo(session).get_by_tg(user.id)

    if client is None:

        return False

    return await advance_to_confirm(

        state,

        session,

        slot_id=slot_id,

        full_name=client.full_name,

        phone=client.phone,

        bot=bot,

        chat_id=chat_id,

        message=message,

    )





async def handle_contact_step_text(

    text: str,

    message: Message,

    state: FSMContext,

    session: AsyncSession,

    *,

    step: str,

    known_tokens: list[str] | None = None,

) -> bool:

    """True если сообщение обработано (cancel/faq/phone/name)."""

    if looks_like_cancel(text):

        await state.clear()

        await message.answer(await step_cancelled(), reply_markup=main_menu())

        return True

    faq = await faq_answer(text)

    if faq:

        await message.answer(faq)

        hint = await (phone_not_now_hint() if step == "phone" else name_prompt())

        await message.answer(hint)

        return True

    if step == "phone" and looks_like_gibberish(text, known_tokens=known_tokens):

        data = await state.get_data()

        attempt = int(data.get("phone_attempts", 0))

        await state.update_data(phone_attempts=attempt + 1)

        await message.answer(await phone_invalid_error(attempt=attempt))

        return True

    return False





async def resolve_name_input(

    text: str,

    message: Message,

    state: FSMContext,

    session: AsyncSession,

) -> str | None:

    if looks_like_same_name(text):

        user = message.from_user

        if user:

            client = await ClientRepo(session).get_by_tg(user.id)

            if client:

                return client.full_name

    if len(text) < 2 or len(text) > 60:

        return None

    return text





async def resolve_phone_and_confirm(

    text: str,

    message: Message,

    state: FSMContext,

    session: AsyncSession,

) -> bool:

    normalized = normalize_phone(text)

    if normalized is None:

        data = await state.get_data()

        attempt = int(data.get("phone_attempts", 0))

        await state.update_data(phone_attempts=attempt + 1)

        await message.answer(await phone_invalid_error(attempt=attempt))

        return True

    data = await state.get_data()

    slot_id = int(data["slot_id"])

    full_name = str(data.get("full_name", ""))

    if message.bot is None:

        return False

    return await advance_to_confirm(

        state,

        session,

        slot_id=slot_id,

        full_name=full_name,

        phone=normalized,

        bot=message.bot,

        chat_id=message.chat.id,

        message=message,

    )





async def begin_confirm_name_edit(message: Message, state: FSMContext) -> None:
    await state.update_data(edit_from_confirm="name", phone_attempts=0)
    await state.set_state(BookingStates.entering_name)
    await message.answer(await name_prompt())





async def begin_confirm_phone_edit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    full_name = str(data.get("full_name", ""))
    first = full_name.split()[0] if full_name else ""
    await state.update_data(edit_from_confirm="phone", phone_attempts=0)
    await state.set_state(BookingStates.entering_phone)
    await message.answer(await phone_after_name(first_name=first))





async def refresh_confirm_card(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> bool:
    data = await state.get_data()
    raw_slot = data.get("slot_id")
    full_name = str(data.get("full_name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    if raw_slot is None or not full_name or not phone:
        await state.clear()
        await message.answer(await say("booking_error", {}), reply_markup=main_menu())
        return False
    if message.bot is None:
        return False
    return await advance_to_confirm(
        state,
        session,
        slot_id=int(raw_slot),
        full_name=full_name,
        phone=phone,
        bot=message.bot,
        chat_id=message.chat.id,
        message=message,
    )





async def try_handle_confirm_contact_edit(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> bool:
    from services.booking_confirm import detect_confirm_contact_edit

    kind, inline = detect_confirm_contact_edit(text)
    if kind == "none":
        return False
    if kind == "name":
        if inline and 2 <= len(inline) <= 60:
            await state.update_data(full_name=inline)
            await refresh_confirm_card(message, state, session)
            return True
        await begin_confirm_name_edit(message, state)
        return True
    if inline:
        await state.update_data(phone=inline)
        await refresh_confirm_card(message, state, session)
        return True
    await begin_confirm_phone_edit(message, state)
    return True


async def handle_confirm_text_input(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Текст на шаге confirm: правка контактов, да/нет, подсказка."""
    from services.booking_confirm import (
        finalize_booking_confirm,
        looks_like_confirm_no,
        looks_like_confirm_yes,
    )
    from services.persona import booking_created, step_cancelled

    if looks_like_cancel(text) or looks_like_confirm_no(text):
        await state.clear()
        await message.answer(await step_cancelled(), reply_markup=main_menu())
        return
    if await try_handle_confirm_contact_edit(text, message, state, session):
        return
    if not looks_like_confirm_yes(text):
        await message.answer(
            await say("confirm_pick_hint", {}),
            reply_markup=confirm_kb(),
        )
        return
    user = message.from_user
    if user is None:
        return
    result = await finalize_booking_confirm(user, state, session)
    if result is None:
        await message.answer(
            "Не удалось подтвердить запись — начните снова 👇",
            reply_markup=main_menu(),
        )
        return
    if result.outcome == "slot_past":
        await message.answer(await say("slot_past", {}), reply_markup=main_menu())
        return
    if result.outcome == "slot_taken":
        await message.answer(await say("slot_just_taken", {}), reply_markup=main_menu())
        return
    await message.answer(
        f"✅ {await booking_created(result.when_str, result.master_name)}",
        reply_markup=main_menu(),
    )
    if result.pending_bookings:
        from bot.handlers.nlu import start_pending_booking_if_any

        await start_pending_booking_if_any(message, state, session, result.pending_bookings)


async def advance_master_from_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master_id: int,
) -> bool:
    """Выбор мастера текстом — тот же шаг, что и кнопка."""
    data = await state.get_data()
    raw_service_id = data.get("service_id")
    if raw_service_id is None:
        return False
    service_id = int(raw_service_id)
    valid_masters = await MasterRepo(session).list_for_service(service_id)
    if not any(m.id == master_id for m in valid_masters):
        return False
    dates = await SlotRepo(session).list_available_dates(master_id, service_id=service_id, days=14)
    if not dates:
        await message.answer(
            await say("master_no_slots_14d", {}),
            reply_markup=main_menu(),
        )
        return True
    service = await ServiceRepo(session).get(service_id)
    price_text = ""
    if service:
        price_text = (
            f"💅 <b>{service_speech_label(service.name)}</b> · "
            f"{service.duration_min} мин · {service.price_kop // 100} ₽\n\n"
        )
    master = await MasterRepo(session).get(master_id)
    master_name = master.name if master else "Мастер"
    await state.update_data(master_id=master_id)
    if await try_period_slot_after_master(message, state, session, master_id):
        return True
    if await continue_after_master_pick(
        message, state, session, service_id=service_id, master_id=master_id,
    ):
        return True
    await state.set_state(BookingStates.choosing_date)
    await message.answer(
        f"{price_text}{await choose_date_prompt(master_name)}",
        reply_markup=dates_kb(dates),
    )
    return True


async def try_master_text_pick(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> bool:
    if await state.get_state() != BookingStates.choosing_master.state:
        return False
    data = await state.get_data()
    raw_service_id = data.get("service_id")
    if raw_service_id is None:
        return False
    masters_for = await MasterRepo(session).list_for_service(int(raw_service_id))
    if not masters_for:
        return False
    hit = find_master_in_text(text, [m.name for m in masters_for])
    if hit:
        master = next(m for m in masters_for if m.name == hit)
        return await advance_master_from_text(message, state, session, master.id)
    await message.answer(
        await choose_master_prompt(),
        reply_markup=masters_kb(masters_for),
    )
    return True
