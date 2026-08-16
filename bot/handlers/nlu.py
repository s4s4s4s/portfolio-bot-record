"""NLU + voice: классификация, запись, короткие ответы менеджера."""
from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path
from tempfile import gettempdir

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.booking_helpers import (
    handle_contact_step_text,
    resolve_name_input,
    resolve_phone_and_confirm,
    try_returning_client_confirm,
)
from bot.keyboards.client import (
    dates_kb,
    main_menu,
    masters_kb,
    services_kb,
    slots_kb,
)
from bot.states import BookingStates, CancelStates, FeedbackStates, RescheduleStates
from core.config import get_settings
from core.logging import get_logger
from db.models import Master, Service, Slot
from db.repositories import BookingRepo, ClientRepo, MasterRepo, ServiceRepo, SlotRepo
from services.booking_cancel import looks_like_cancel_intent, looks_like_my_bookings
from services.booking_fsm_text import (
    looks_like_date_correction,
    looks_like_later_time_request,
    looks_like_waitlist_request,
    parse_min_time_hint,
    safe_client_first_name,
)
from services.booking_hints import (
    apply_hints,
    clear_pending_hints,
    extract_date_time,
    merge_hints,
)
from services.complaint_detect import (
    looks_like_cancel,
    looks_like_change_master,
    looks_like_change_mind,
    looks_like_complaint,
    looks_like_gibberish,
    looks_like_off_topic,
    looks_like_phone_update,
)
from services.copy_variants import date_step_nudge, slot_step_nudge
from services.faq_price import (
    looks_like_price_followup,
    looks_like_price_question,
    try_answer_price,
)
from services.feedback_store import save_complaint_feedback
from services.human_reply import say
from services.llm_client import LLMClient, get_llm_client
from services.master_matching import find_master_in_text, find_master_name
from services.multi_booking import (
    BookingSegment,
    extract_booking_segments,
    looks_like_booking_request,
)
from services.nlu import (
    _best_match,
    _resolve_date,
    classify_intent,
    generate_fsm_message,
    generate_redirect_reply,
)
from services.period_offer import extract_time_of_day
from services.persona import (
    alternative_slot_prompt,
    booking_short_line,
    choose_date_prompt,
    choose_master_prompt,
    choose_slot_prompt,
    complaint_recovery_message,
    date_corrected_ack,
    did_not_understand_message,
    faq_answer,
    feedback_thanks,
    free_chat_message,
    help_text,
    invalid_master_for_service,
    later_slots_unavailable,
    master_card_line,
    masters_list_intro,
    multi_booking_continue,
    multi_booking_plan,
    name_length_error,
    off_topic_message,
    phone_after_name,
    reschedule_done,
    returning_booking_ack,
    service_choice_prompt,
    unsupported_service_message,
    waitlist_not_available_yet,
    welcome_with_catalog,
)
from services.reschedule_detect import looks_like_reschedule
from services.salon_time import is_past_date
from services.service_aliases import detect_unsupported_service, normalize_service_hint
from services.service_grammar import no_masters_message_async, service_speech_label
from services.slot_matching import (
    filter_slots_exact,
    nearest_slot_to_time,
    parse_time_hint,
)
from services.voice_recognition import download_voice_file, transcribe_file

log = get_logger()
router = Router(name="nlu")

_AVAILABILITY_RE = re.compile(
    r"(свобод|когда\s+.+\s+будет|есть\s+ли\s+окн|какие\s+окн|во\s+сколько)",
    re.IGNORECASE,
)


def _is_nlu_enabled() -> bool:
    return get_settings().enable_nlu


def _is_voice_enabled() -> bool:
    return get_settings().enable_voice


async def _answer_with_menu(
    message: Message,
    text: str,
    *,
    in_fsm: bool,
    step_kb: InlineKeyboardMarkup | None = None,
) -> None:
    markup = step_kb if step_kb is not None else (None if in_fsm else main_menu())
    await message.answer(text, reply_markup=markup)


async def _re_prompt_fsm_step(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    services: list[Service],
    masters: list[Master],
) -> None:
    """Не сбрасывать FSM — повторить текущий шаг с кнопками."""
    current = await state.get_state()
    data = await state.get_data()
    if current == BookingStates.choosing_service.state:
        await message.answer(await say("pick_service", {}), reply_markup=services_kb(services))
        return
    if current == BookingStates.choosing_master.state:
        sid = data.get("service_id")
        if sid:
            masters_for = await MasterRepo(session).list_for_service(int(sid))
            await message.answer(await choose_master_prompt(), reply_markup=masters_kb(masters_for))
            return
    if current == BookingStates.choosing_date.state:
        sid, mid = data.get("service_id"), data.get("master_id")
        if sid and mid:
            dates = await SlotRepo(session).list_available_dates(int(mid), service_id=int(sid), days=14)
            master = await MasterRepo(session).get(int(mid))
            name = master.name if master else "мастеру"
            await message.answer(await choose_date_prompt(name), reply_markup=dates_kb(dates))
            return
    if current == BookingStates.choosing_slot.state:
        sid, mid = data.get("service_id"), data.get("master_id")
        saved = data.get("target_date")
        if sid and mid and saved:
            target = _date.fromisoformat(saved)
            slots = await SlotRepo(session).list_available_on_date(int(mid), target, int(sid))
            master = await MasterRepo(session).get(int(mid))
            name = master.name if master else "мастер"
            if slots:
                times = [s.start_at.strftime("%H:%M") for s in slots]
                await message.answer(
                    await choose_slot_prompt(name, target.strftime("%d.%m"), times=times),
                    reply_markup=slots_kb(slots),
                )
                return
    await message.answer(await say("fsm_type_hint", {}), reply_markup=main_menu())


def _fsm_step_label(state: str | None) -> str:
    if state == BookingStates.choosing_service.state:
        return "выбор услуги"
    if state == BookingStates.choosing_master.state:
        return "выбор мастера"
    if state == BookingStates.choosing_date.state:
        return "выбор даты"
    if state == BookingStates.choosing_slot.state:
        return "выбор времени"
    if state == BookingStates.entering_name.state:
        return "имя для записи"
    if state == BookingStates.entering_phone.state:
        return "номер телефона"
    return ""


async def _handle_off_topic(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    services: list[Service],
    masters: list[Master],
    *,
    in_fsm: bool,
) -> None:
    svc_names = [s.name for s in services]
    step = _fsm_step_label(await state.get_state()) if in_fsm else ""
    reply = await off_topic_message(
        services=svc_names,
        step=step,
        user_text=text,
    )
    if in_fsm:
        await message.answer(reply)
        await _re_prompt_fsm_step(message, state, session, services, masters)
        return
    await _answer_with_menu(message, reply, in_fsm=False)


async def _handle_free_chat(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    services: list[Service],
    masters: list[Master],
    *,
    in_fsm: bool,
) -> None:
    svc_names = [s.name for s in services]
    step = _fsm_step_label(await state.get_state()) if in_fsm else ""
    reply = await free_chat_message(services=svc_names, step=step, user_text=text)
    if in_fsm:
        await message.answer(reply)
        await _re_prompt_fsm_step(message, state, session, services, masters)
        return
    await _answer_with_menu(message, reply, in_fsm=False)


# ── Voice ───────────────────────────────────────────────────────────────

@router.message(F.content_type == "voice")
async def msg_voice(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    if not _is_voice_enabled():
        await message.answer(
            await say("menu_hint", {}),
            reply_markup=main_menu(),
        )
        return
    settings = get_settings()
    if not settings.groq_api_key:
        await message.answer(
            await say("menu_hint", {}),
            reply_markup=main_menu(),
        )
        return
    voice = message.voice
    if voice is None:
        return

    tmp = Path(gettempdir()) / f"voice_{voice.file_id}.ogg"
    await message.answer(await say("voice_listening", {}))
    await download_voice_file(message.bot, voice.file_id, tmp)
    text = await transcribe_file(tmp)
    tmp.unlink(missing_ok=True)

    if not text:
        await message.answer(
            await say("voice_failed", {}),
            reply_markup=main_menu(),
        )
        return

    await _handle_user_text(text, message, state, session)


# ── Free text ───────────────────────────────────────────────────────────

_ACTIVE_BOOKING_STATES = (
    BookingStates.choosing_master,
    BookingStates.choosing_date,
    BookingStates.choosing_slot,
)

_NLU_ALLOWED_STATES = (
    BookingStates.choosing_service,
    BookingStates.choosing_master,
    BookingStates.choosing_date,
    BookingStates.choosing_slot,
    BookingStates.entering_name,
    BookingStates.entering_phone,
    RescheduleStates.choosing_date,
    RescheduleStates.choosing_slot,
)


@router.message(F.content_type == "text", ~F.text.startswith("/"), StateFilter(None))
async def msg_nlu_text_no_state(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if not _is_nlu_enabled():
        await message.answer(await say("menu_hint", {}), reply_markup=main_menu())
        return
    await _handle_user_text(text, message, state, session)


@router.message(F.text, ~F.text.startswith("/"), StateFilter(FeedbackStates.awaiting_complaint_feedback))
async def msg_complaint_feedback(
    message: Message, state: FSMContext,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    user = message.from_user
    if user:
        save_complaint_feedback(tg_user_id=user.id, text=text)
    await state.clear()
    await message.answer(await feedback_thanks(), reply_markup=main_menu())


@router.message(F.text, ~F.text.startswith("/"), StateFilter(*_NLU_ALLOWED_STATES))
async def msg_nlu_text_in_fsm(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if not _is_nlu_enabled():
        await message.answer(await say("fsm_type_hint", {}))
        return
    await _handle_user_text(text, message, state, session)


def _heuristic_intent(
    text: str, entities: dict[str, str], *, service_names: list[str] | None = None,
) -> str | None:
    low = text.lower()
    if looks_like_my_bookings(text):
        return "my"
    if any(w in low for w in ("отмен", "стоп", "не надо")):
        return "cancel"
    if _AVAILABILITY_RE.search(low) or any(
        w in low for w in ("запиш", "запиши", "запишите", "записаться", "хочу на", "нужен", "нужна", "давай", "давайте")
    ):
        return "book"
    if service_names and looks_like_booking_request(text, service_names):
        return "book"
    if service_names:
        from services.nlu import _best_match

        if _best_match(text.strip(), service_names):
            return "book"
    if "помощ" in low or "как запис" in low:
        return "help"
    return None


async def _handle_user_text(
    text: str, message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    llm = get_llm_client()
    services = await ServiceRepo(session).list_active()
    masters = await MasterRepo(session).list_active()
    svc_names = [s.name for s in services]
    mst_names = [m.name for m in masters]

    nlu = await classify_intent(text, llm, services=svc_names, masters=mst_names)
    intent = nlu.get("intent", "other")
    entities: dict[str, str] = dict(nlu.get("entities") or {})

    heuristic = _heuristic_intent(text, entities, service_names=svc_names)
    if heuristic:
        intent = heuristic

    segments = extract_booking_segments(text, svc_names)
    if len(segments) >= 2:
        intent = "book"

    current_state = await state.get_state()
    if current_state in (BookingStates.choosing_date, BookingStates.choosing_slot):
        lower_text = text.lower()
        if any(w in lower_text for w in ("другой", "другого", "поменять", "сменить", "иной")):
            intent = "book"
            data = await state.get_data()
            sid = data.get("service_id")
            if sid:
                svc = await ServiceRepo(session).get(sid)
                if svc:
                    entities["service_name"] = svc.name
        parsed_date, parsed_time = extract_date_time(text)
        if parsed_date or parsed_time:
            intent = "book"
            if parsed_date:
                entities["date_hint"] = parsed_date
            if parsed_time:
                entities["time_hint"] = parsed_time
            data = await state.get_data()
            if not entities.get("service_name") and data.get("service_id"):
                svc = await ServiceRepo(session).get(data["service_id"])
                if svc:
                    entities["service_name"] = svc.name
            if not entities.get("master_name") and data.get("master_id"):
                mst = await MasterRepo(session).get(data["master_id"])
                if mst:
                    entities["master_name"] = mst.name

    if intent == "masters" and _AVAILABILITY_RE.search(text):
        intent = "book"

    log.info("NLU: intent=%s entities=%s", intent, entities)

    if current_state == BookingStates.confirm.state:
        from bot.handlers.booking_helpers import handle_confirm_text_input

        await handle_confirm_text_input(text, message, state, session)
        return

    if current_state in (
        RescheduleStates.choosing_date.state,
        RescheduleStates.choosing_slot.state,
    ):
        from bot.handlers.reschedule import handle_reschedule_text

        if await handle_reschedule_text(text, message, state, session):
            return

    if looks_like_reschedule(text):
        from bot.handlers.reschedule import start_reschedule

        await start_reschedule(message, state, session)
        return

    if looks_like_my_bookings(text):
        await state.clear()
        from bot.handlers.my import _show_bookings
        await _show_bookings(
            message, session, tg_user_id=message.from_user.id if message.from_user else None,
        )
        return

    in_fsm = current_state is not None
    known_tokens = svc_names + mst_names

    if current_state == BookingStates.entering_name.state:
        if await handle_contact_step_text(text, message, state, session, step="name", known_tokens=known_tokens):
            return
        resolved = await resolve_name_input(text, message, state, session)
        if resolved is None:
            await message.answer(await name_length_error())
            return
        await state.update_data(full_name=resolved)
        data = await state.get_data()
        if data.get("edit_from_confirm") == "name":
            from bot.handlers.booking_helpers import refresh_confirm_card

            await refresh_confirm_card(message, state, session)
            return
        await state.set_state(BookingStates.entering_phone)
        await message.answer(await phone_after_name(first_name=resolved))
        return

    if current_state == BookingStates.entering_phone.state:
        if await handle_contact_step_text(text, message, state, session, step="phone", known_tokens=known_tokens):
            return
        await resolve_phone_and_confirm(text, message, state, session)
        return

    from bot.handlers.booking_helpers import try_master_text_pick

    if await try_master_text_pick(text, message, state, session):
        return

    if looks_like_off_topic(text):
        await _handle_off_topic(text, message, state, session, services, masters, in_fsm=in_fsm)
        return

    if looks_like_change_mind(text):
        await _intent_cancel(message, state, session)
        return

    if looks_like_complaint(text):
        await _intent_complaint_recovery(message, state, session)
        return

    if looks_like_phone_update(text):
        await _intent_update_phone(text, message, session)
        return

    if looks_like_change_master(text):
        handled = await _intent_change_master(text, message, session, masters, services)
        if handled:
            return

    data = await state.get_data()
    pending_price_sid = data.get("pending_after_price_service_id")
    if (
        pending_price_sid
        and not in_fsm
        and looks_like_price_followup(text)
    ):
        await state.update_data(pending_after_price_service_id=None)
        svc = await ServiceRepo(session).get(int(pending_price_sid))
        if svc:
            entities = dict(entities)
            entities["service_name"] = svc.name
            await _intent_book(text, message, state, session, entities, services, masters, llm)
            return

    if looks_like_price_question(text):
        price_reply = await try_answer_price(text, session, state)
        if price_reply:
            await _answer_with_menu(message, price_reply, in_fsm=in_fsm)
            return

    unsupported = detect_unsupported_service(text)
    if unsupported and not in_fsm:
        svc_names_list = [s.name for s in services]
        await message.answer(
            await unsupported_service_message(
                unsupported.label, svc_names_list, quoted=unsupported.quoted, user_text=text,
            ),
            reply_markup=services_kb(services),
        )
        return

    if current_state in _ACTIVE_BOOKING_STATES:
        if looks_like_cancel(text):
            await _intent_cancel(message, state, session)
            return
        if await _handle_active_booking_text(
            text, message, state, session, services, masters, llm,
        ):
            return

    faq = await faq_answer(text)
    if faq:
        await _answer_with_menu(message, faq, in_fsm=in_fsm)
        return

    data = await state.get_data()
    if data.get("refused_booking") and intent == "book":
        await message.answer(
            await say("booking_refused_ack", {}),
            reply_markup=main_menu(),
        )
        return

    if intent == "book":
        if current_state in (BookingStates.choosing_date, BookingStates.choosing_slot):
            parsed_date, parsed_time = extract_date_time(text)
            has_new_hint = bool(parsed_date or parsed_time or entities.get("date_hint") or entities.get("time_hint"))
            if not has_new_hint and not segments:
                nudge = await date_step_nudge() if current_state == BookingStates.choosing_date else await slot_step_nudge()
                await message.answer(nudge)
                return
        if len(segments) >= 2:
            await _intent_multi_book(message, state, session, segments, services, masters, llm)
            return
        await _intent_book(text, message, state, session, entities, services, masters, llm)
        return

    if intent == "cancel":
        in_cancel_fsm = current_state in (
            CancelStates.pick_booking.state,
            CancelStates.confirm_cancel_all.state,
        )
        if looks_like_cancel_intent(text, in_cancel_fsm=in_cancel_fsm):
            await _intent_cancel(message, state, session)
            return
        if looks_like_off_topic(text):
            await _handle_off_topic(text, message, state, session, services, masters, in_fsm=in_fsm)
            return
        intent = "other"

    if intent == "help":
        await message.answer(await help_text(), parse_mode="HTML", reply_markup=None if in_fsm else main_menu())
        return

    if intent == "my":
        from bot.handlers.my import _show_bookings
        await _show_bookings(
            message, session, tg_user_id=message.from_user.id if message.from_user else None,
        )
        return

    if intent == "masters":
        await _intent_masters(message, state, session, masters, services)
        return

    if intent == "smalltalk":
        if in_fsm:
            await _handle_off_topic(text, message, state, session, services, masters, in_fsm=True)
            return
        greet = await welcome_with_catalog(svc_names)
        if "салам" in text.lower() or "ас-салам" in text.lower():
            reply = f"Ва алейкум ас-салам! 👋\n{greet}"
        else:
            reply = greet
        await _answer_with_menu(message, reply, in_fsm=in_fsm)
        return

    if looks_like_gibberish(text, known_tokens=known_tokens):
        if in_fsm:
            await _re_prompt_fsm_step(message, state, session, services, masters)
            return
        await _answer_with_menu(message, await did_not_understand_message(), in_fsm=in_fsm)
        return

    reply = await generate_redirect_reply(text, llm)
    if in_fsm:
        await _re_prompt_fsm_step(message, state, session, services, masters)
        return
    await _answer_with_menu(message, reply, in_fsm=in_fsm)


async def _intent_complaint_recovery(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    settings = get_settings()
    msg = await complaint_recovery_message(
        promo=settings.salon_recovery_promo.strip(),
        admin_contact=settings.salon_admin_contact.strip(),
    )
    await state.clear()
    await state.set_state(FeedbackStates.awaiting_complaint_feedback)
    await state.update_data(refused_booking=True)
    await message.answer(msg, reply_markup=main_menu())


async def _intent_update_phone(
    text: str, message: Message, session: AsyncSession,
) -> None:
    from services.phone import normalize_phone

    normalized = normalize_phone(text)
    if normalized is None:
        for word in text.split():
            normalized = normalize_phone(word)
            if normalized:
                break
    user = message.from_user
    if user is None or normalized is None:
        await message.answer(await say("phone_not_understood", {}))
        return
    await ClientRepo(session).upsert(
        tg_user_id=user.id,
        tg_username=user.username,
        full_name=user.full_name or "Клиент",
        phone=normalized,
    )
    await message.answer(await say("phone_saved", {}), reply_markup=main_menu())


async def _intent_change_master(
    text: str,
    message: Message,
    session: AsyncSession,
    masters: list[Master],
    services: list[Service],
) -> bool:
    user = message.from_user
    if user is None:
        return False
    client = await ClientRepo(session).get_by_tg(user.id)
    if client is None:
        return False
    active = await BookingRepo(session).list_active_for_client(client.id)
    if not active:
        return False
    booking = active[0]
    slot = booking.slot
    if not slot:
        return False
    target_master = None
    low = text.lower()
    for m in masters:
        if m.name.lower() in low and m.id != slot.master_id:
            target_master = m
            break
    if target_master is None:
        return False
    service = slot.service
    if not service:
        return False
    masters_for = await MasterRepo(session).list_for_service(service.id)
    if target_master not in masters_for:
        await message.answer(
            await invalid_master_for_service(target_master.name, service.name, [x.name for x in masters_for]),
            reply_markup=main_menu(),
        )
        return True
    new_slots = await SlotRepo(session).list_available_on_date(
        target_master.id, slot.start_at.date(), service.id,
    )
    new_slot = next((s for s in new_slots if s.start_at == slot.start_at), None)
    if new_slot is None and new_slots:
        new_slot = new_slots[0]
    if new_slot is None:
        await message.answer(
            await say("change_master_no_slots", {"master": target_master.name}),
            reply_markup=main_menu(),
        )
        return True
    old_slot = await SlotRepo(session).get(slot.id)
    if old_slot:
        old_slot.status = "available"
        old_slot.booking_id = None
    reserved = await SlotRepo(session).reserve_atomic(new_slot.id)
    if reserved is None:
        await message.answer(await say("slot_just_taken", {}), reply_markup=main_menu())
        return True
    booking.slot_id = new_slot.id
    reserved.booking_id = booking.id
    await session.flush()
    when = new_slot.start_at.strftime("%d.%m %H:%M")
    await message.answer(
        await reschedule_done(service.name, target_master.name, when),
        reply_markup=main_menu(),
    )
    return True


async def _handle_active_booking_text(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    services: list[Service],
    masters: list[Master],
    llm: LLMClient,
) -> bool:
    """Текст на шаге дата/время — не сбрасывать FSM и не слать «выберите услугу»."""
    data = await state.get_data()
    sid = data.get("service_id")
    mid = data.get("master_id")
    if not sid or not mid:
        return False
    service = next((s for s in services if s.id == sid), None)
    master = next((m for m in masters if m.id == mid), None)
    if service is None or master is None:
        return False

    if looks_like_waitlist_request(text):
        await message.answer(await waitlist_not_available_yet())
        return True

    parsed_date, parsed_time = extract_date_time(text)
    if parsed_date or parsed_time:
        await apply_hints(state, parsed_date, parsed_time)
        data = await state.get_data()
        date_hint, time_hint = merge_hints(data, parsed_date, parsed_time)
        if looks_like_date_correction(text) and parsed_date:
            label = _date.fromisoformat(parsed_date).strftime("%d.%m")
            await message.answer(await date_corrected_ack(label))
        await _show_availability(
            message, state, session, service, master, date_hint, time_hint, llm,
        )
        return True

    if looks_like_later_time_request(text):
        min_time = parse_min_time_hint(text)
        saved = data.get("target_date")
        if not saved:
            return False
        target = _date.fromisoformat(saved)
        all_slots = await SlotRepo(session).list_available_on_date(
            master.id, target, service.id,
        )
        if min_time:
            from services.slot_matching import parse_time_hint as _pt

            parsed = _pt(min_time)
            if parsed:
                h, mi = parsed
                later = [
                    s for s in all_slots
                    if s.start_at.hour > h or (s.start_at.hour == h and s.start_at.minute > mi)
                ]
                if later:
                    await state.set_state(BookingStates.choosing_slot)
                    await message.answer(
                        f"Позже {min_time} есть такие окна 👇",
                        reply_markup=slots_kb(later),
                    )
                    return True
                latest = all_slots[-1].start_at.strftime("%H:%M") if all_slots else min_time
                await message.answer(await later_slots_unavailable(latest))
                if all_slots:
                    times = [s.start_at.strftime("%H:%M") for s in all_slots]
                    await message.answer(
                        await choose_slot_prompt(master.name, target.strftime("%d.%m"), times=times),
                        reply_markup=slots_kb(all_slots),
                    )
                return True
        await message.answer(
            "Напишите, на какое время ориентироваться — например «после 18:00» — "
            "или выберите кнопкой 👇",
        )
        return True

    return False


def _segments_to_pending(segments: list[BookingSegment]) -> list[dict[str, str]]:
    return [
        {"service_name": s.service_name, "date_hint": s.date_hint, "date_label": s.date_label}
        for s in segments
    ]


async def _intent_multi_book(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    segments: list[BookingSegment],
    services: list[Service],
    masters: list[Master],
    llm: LLMClient,
) -> None:
    plan_lines = [(s.service_name, s.date_label) for s in segments]
    await message.answer(await multi_booking_plan(plan_lines))
    rest = segments[1:]
    first = segments[0]
    await state.update_data(pending_bookings=_segments_to_pending(rest))
    entities = {"service_name": first.service_name, "date_hint": first.date_hint}
    await _intent_book(
        f"{first.service_name} {first.date_hint}",
        message, state, session, entities, services, masters, llm,
    )


async def start_pending_booking_if_any(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    pending: list[dict[str, str]],
) -> bool:
    """После успешной записи — следующий сегмент из очереди."""
    if not pending:
        return False
    nxt = pending[0]
    rest = pending[1:]
    await state.update_data(pending_bookings=rest)
    await message.answer(
        await multi_booking_continue(nxt["service_name"], nxt.get("date_label", "")),
    )
    services = await ServiceRepo(session).list_active()
    masters = await MasterRepo(session).list_active()
    entities = {
        "service_name": nxt["service_name"],
        "date_hint": nxt.get("date_hint", ""),
    }
    await _intent_book(
        nxt["service_name"],
        message, state, session, entities, services, masters, get_llm_client(),
    )
    return True


async def _intent_book(
    text: str,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    entities: dict[str, str],
    services: list[Service],
    masters: list[Master],
    llm: LLMClient,
) -> None:
    current_state = await state.get_state()
    if current_state in (BookingStates.choosing_date, BookingStates.choosing_slot):
        parsed_date, parsed_time = extract_date_time(text)
        data = await state.get_data()
        merged_date, merged_time = merge_hints(
            data,
            parsed_date or entities.get("date_hint", ""),
            parsed_time or entities.get("time_hint", ""),
        )
        if not (
            parsed_date or parsed_time
            or merged_date or merged_time
            or entities.get("date_hint") or entities.get("time_hint")
        ):
            nudge = await date_step_nudge() if current_state == BookingStates.choosing_date else await slot_step_nudge()
            await message.answer(nudge)
            return

    svc_name_hint = normalize_service_hint(entities.get("service_name", ""))
    mst_name_hint = entities.get("master_name", "")
    date_hint = entities.get("date_hint", "")
    time_hint = entities.get("time_hint", "")

    parsed_date, parsed_time = extract_date_time(text)
    if parsed_date:
        date_hint = parsed_date
    if parsed_time:
        time_hint = parsed_time
    await apply_hints(state, parsed_date, parsed_time)
    data = await state.get_data()
    date_hint, time_hint = merge_hints(data, date_hint, time_hint)

    if not services:
        await message.answer(
            "Услуги ещё не настроены — попросите администратора.",
            reply_markup=main_menu(),
        )
        return

    service = None
    if svc_name_hint:
        match = _best_match(svc_name_hint, [s.name for s in services])
        if match:
            service = next((s for s in services if s.name == match), None)
    if not service and text:
        match = _best_match(text, [s.name for s in services])
        if match:
            service = next((s for s in services if s.name == match), None)
    if not service and text:
        low = text.lower()
        for s in services:
            stem = s.name.split("(")[0].strip().lower()
            if len(stem) >= 4 and stem[:5] in low:
                service = s
                break

    if not service and current_state in (
        BookingStates.choosing_date,
        BookingStates.choosing_slot,
        BookingStates.choosing_master,
    ):
        data = await state.get_data()
        sid = data.get("service_id")
        if sid:
            service = next((s for s in services if s.id == sid), None)

    master = None
    mst_names = [m.name for m in masters]
    if mst_name_hint:
        match = find_master_name(mst_name_hint, mst_names) or _best_match(mst_name_hint, mst_names)
        if match:
            master = next((m for m in masters if m.name == match), None)
    if not master and text:
        hit = find_master_in_text(text, mst_names)
        if hit:
            master = next((m for m in masters if m.name == hit), None)

    if not master and current_state in (BookingStates.choosing_date, BookingStates.choosing_slot):
        data = await state.get_data()
        mid = data.get("master_id")
        if mid:
            master = next((m for m in masters if m.id == mid), None)

    svc_names = [s.name for s in services]
    unsupported = detect_unsupported_service(text, svc_name_hint)
    if unsupported and not service:
        await message.answer(
            await unsupported_service_message(
                unsupported.label, svc_names, quoted=unsupported.quoted, user_text=text,
            ),
            reply_markup=services_kb(services),
        )
        await state.set_state(BookingStates.choosing_service)
        return

    user = message.from_user
    returning_client = None
    if user:
        returning_client = await ClientRepo(session).get_by_tg(user.id)
    in_active_booking = current_state in (
        BookingStates.choosing_service,
        BookingStates.choosing_master,
        BookingStates.choosing_date,
        BookingStates.choosing_slot,
        BookingStates.entering_name,
        BookingStates.entering_phone,
        BookingStates.confirm,
    )
    if (
        returning_client
        and not in_active_booking
        and (master or date_hint or time_hint)
        and not service
        and current_state not in (
            RescheduleStates.choosing_date.state,
            RescheduleStates.choosing_slot.state,
            RescheduleStates.pick_booking.state,
        )
    ):
        short = safe_client_first_name(returning_client.full_name)
        ack = await returning_booking_ack(short)
        svc_options = [s.name for s in services]
        await message.answer(
            f"{ack}\n{await service_choice_prompt(svc_options)}",
            reply_markup=services_kb(services),
        )
        await state.set_state(BookingStates.choosing_service)
        return

    if not service and not master:
        msg = await generate_fsm_message("choose_service", llm)
        await message.answer(msg, reply_markup=services_kb(services))
        await state.set_state(BookingStates.choosing_service)
        return

    if not service and master:
        for svc in services:
            mfs = await MasterRepo(session).list_for_service(svc.id)
            if any(x.id == master.id for x in mfs):
                service = svc
                break

    if not service:
        if unsupported:
            await message.answer(
                await unsupported_service_message(
                    unsupported.label, svc_names, quoted=unsupported.quoted, user_text=text,
                ),
                reply_markup=services_kb(services),
            )
        else:
            msg = await generate_fsm_message("choose_service", llm)
            await message.answer(msg, reply_markup=services_kb(services))
        await state.set_state(BookingStates.choosing_service)
        return

    await state.update_data(service_id=service.id)
    price = service.price_kop // 100
    masters_for_svc = await MasterRepo(session).list_for_service(service.id)

    if not masters_for_svc:
        await message.answer(
            await no_masters_message_async(service.name),
            reply_markup=services_kb(services),
        )
        await state.set_state(BookingStates.choosing_service)
        return

    if master and master not in masters_for_svc:
        alt_names = [m.name for m in masters_for_svc]
        await message.answer(
            await invalid_master_for_service(master.name, service.name, alt_names),
            reply_markup=masters_kb(masters_for_svc),
        )
        await state.set_state(BookingStates.choosing_master)
        return

    if not master:
        period = extract_time_of_day(text)
        if period and date_hint and not time_hint:
            try:
                target = _date.fromisoformat(date_hint)
            except ValueError:
                target = None
            if target is not None:
                from services.period_offer import try_start_period_master_shortcut

                if await try_start_period_master_shortcut(
                    message, state, session, service, target, period,
                ):
                    return
        if date_hint and not time_hint and not period:
            try:
                target = _date.fromisoformat(date_hint)
            except ValueError:
                target = None
            if target is not None:
                from services.date_master_offer import try_start_date_master_shortcut

                if await try_start_date_master_shortcut(
                    message, state, session, service, target,
                ):
                    return
        if len(masters_for_svc) == 1:
            master = masters_for_svc[0]
        else:
            await message.answer(booking_short_line(service.name, service.duration_min, price))
            await message.answer(
                await choose_master_prompt(),
                reply_markup=masters_kb(masters_for_svc),
            )
            await state.set_state(BookingStates.choosing_master)
            return

    await state.update_data(master_id=master.id)
    await _show_availability(
        message, state, session, service, master, date_hint, time_hint, llm,
    )


async def _advance_after_slot_pick(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    slot: Slot,
) -> None:
    await state.update_data(slot_id=slot.id)
    await clear_pending_hints(state)
    if await try_returning_client_confirm(message, state, session, slot.id):
        return
    await state.set_state(BookingStates.entering_name)
    time_label = slot.start_at.strftime("%H:%M")
    await message.answer(await say("slot_time_ack", {"time": time_label}))


async def _show_availability(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    service: Service,
    master: Master,
    date_hint: str,
    time_hint: str,
    llm: LLMClient,
) -> None:
    _ = llm
    price = service.price_kop // 100
    slot_repo = SlotRepo(session)
    current_state = await state.get_state()

    data = await state.get_data()
    date_hint, time_hint = merge_hints(data, date_hint, time_hint)

    target_date = _resolve_date(date_hint) if date_hint else None
    if not target_date and current_state in (BookingStates.choosing_date, BookingStates.choosing_slot):
        data = await state.get_data()
        saved = data.get("target_date")
        if saved:
            target_date = _date.fromisoformat(saved)

    if target_date and is_past_date(target_date):
        await message.answer(await say("day_past", {}))
        target_date = None

    data = await state.get_data()
    if target_date:
        all_slots = await slot_repo.list_available_on_date(master.id, target_date, service.id)
        date_label = target_date.strftime("%d.%m")
        await state.update_data(target_date=target_date.isoformat())
        same_slot_step = (
            current_state == BookingStates.choosing_slot.state
            and data.get("service_id") == service.id
            and data.get("master_id") == master.id
        )
        if not same_slot_step:
            await message.answer(booking_short_line(service.name, service.duration_min, price))

        if time_hint and all_slots:
            exact = filter_slots_exact(all_slots, time_hint)
            if len(exact) == 1:
                await _advance_after_slot_pick(message, state, session, exact[0])
                return
            parsed = parse_time_hint(time_hint)
            if parsed and not exact:
                nearest, delta_min = nearest_slot_to_time(all_slots, target_date, time_hint)
                if nearest and 0 < delta_min <= 60:
                    req = f"{parsed[0]:02d}:{parsed[1]:02d}"
                    off = nearest.start_at.strftime("%H:%M")
                    await state.set_state(BookingStates.choosing_slot)
                    await message.answer(
                        await alternative_slot_prompt(req, off, delta_min),
                        reply_markup=slots_kb([nearest]),
                    )
                    return

        if all_slots:
            await state.set_state(BookingStates.choosing_slot)
            if same_slot_step:
                await message.answer(await slot_step_nudge())
                return
            times = [s.start_at.strftime("%H:%M") for s in all_slots]
            await message.answer(
                await choose_slot_prompt(master.name, date_label, times=times),
                reply_markup=slots_kb(all_slots),
            )
            return
        from services.date_master_offer import (
            say_date_miss_no_alts,
            try_alternate_masters_for_date,
        )

        if await try_alternate_masters_for_date(
            message, state, session, service, master, target_date,
        ):
            return
        dates = await slot_repo.list_available_dates(master.id, service_id=service.id, days=14)
        if dates:
            await state.set_state(BookingStates.choosing_date)
            await message.answer(
                await say_date_miss_no_alts(master.name, target_date),
                reply_markup=dates_kb(dates),
            )
            return

    dates = await slot_repo.list_available_dates(master.id, service_id=service.id, days=14)
    if not dates:
        await message.answer(
            await say("no_dates", {"master": master.name}),
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    same_step = (
        current_state == BookingStates.choosing_date.state
        and data.get("service_id") == service.id
        and data.get("master_id") == master.id
        and not date_hint
    )
    if same_step:
        await message.answer(await date_step_nudge())
        return

    await state.set_state(BookingStates.choosing_date)
    if data.get("service_id") != service.id or data.get("master_id") != master.id:
        await message.answer(booking_short_line(service.name, service.duration_min, price))
    await message.answer(
        await choose_date_prompt(master.name),
        reply_markup=dates_kb(dates),
    )


async def _intent_cancel(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    from bot.handlers.cancel_booking import handle_cancel_request

    text = (message.text or "").strip() or "отмена"
    await handle_cancel_request(message, state, session, text=text)


async def _intent_masters(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    masters: list[Master],
    services: list[Service],
) -> None:
    if not masters:
        await message.answer(
            "Мастера ещё не добавлены. Напишите администратору или попробуйте позже.",
            reply_markup=main_menu(),
        )
        return

    svc_by_id = {s.id: s.name for s in services}
    lines = [await masters_list_intro()]
    for m in masters:
        names: list[str] = []
        if m.services_csv:
            for part in m.services_csv.split(","):
                part = part.strip()
                if part.isdigit():
                    sid = int(part)
                    if sid in svc_by_id:
                        names.append(service_speech_label(svc_by_id[sid]))
        lines.append(master_card_line(m.name, ", ".join(names) if names else "—"))

    in_fsm = await state.get_state() is not None
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=None if in_fsm else main_menu(),
    )
