"""Persona салона: LLM-ответы + форматирование данных (не диалог)."""

from __future__ import annotations

import re

from core.config import get_settings
from services import human_reply
from services.booking_format import fmt_booking_card, fmt_booking_summary, fmt_confirm_body
from services.llm_client import LLMClient

_FAQ_ASK_PATTERNS = re.compile(

    r"(что такое|что это|объясни|расскаж|какой лак|какие лак|бренд|фирм|"

    r"можно с|можно ли|разреш|прийти|привести|подскаж|скажите|"

    r"собак|собач|питомц|животн|"

    r"\bкот(?:ик|а|у|ом|ы)?\b|\bкош)",

    re.IGNORECASE,

)

_PET_FAQ_RE = re.compile(

    r"собак|собач|питомц|животн|\bкот(?:ик|а|у|ом|ы)?\b|\bкош",

    re.IGNORECASE,

)



__all__ = [

    "alternative_slot_prompt",
    "availability_intro",
    "booking_cancelled",
    "booking_cancelled_detail",
    "booking_created",
    "booking_ready_intro",
    "booking_short_line",
    "cancel_all_confirm_prompt",
    "cancel_all_done",
    "cancel_booking_button_label",
    "cancel_booking_not_found_hint",
    "cancel_which_booking_prompt",
    "choose_date_prompt",
    "choose_master_prompt",
    "choose_slot_prompt",
    "complaint_recovery_message",
    "confirm_intro",
    "date_corrected_ack",
    "did_not_understand_message",
    "faq_answer",
    "feedback_thanks",
    "fmt_booking_card",
    "fmt_booking_summary",
    "fmt_confirm_body",
    "greeting_message",
    "help_text",
    "invalid_master_for_service",
    "later_slots_unavailable",
    "looks_like_faq_request",
    "master_card_line",
    "masters_list_intro",
    "multi_booking_continue",
    "multi_booking_plan",
    "name_length_error",
    "name_prompt",
    "no_slots_prompt",
    "phone_after_name",
    "phone_invalid_error",
    "phone_not_now_hint",
    "redirect_message",
    "reschedule_done",
    "returning_booking_ack",
    "service_choice_prompt",
    "step_cancelled",
    "unsupported_service_message",
    "waitlist_not_available_yet",
    "welcome_with_catalog",

]





def looks_like_faq_request(text: str) -> bool:

    return bool(_FAQ_ASK_PATTERNS.search(text))





async def redirect_message(*, user_text: str = "", llm: LLMClient | None = None) -> str:

    return await human_reply.say("redirect", {}, user_text=user_text, llm=llm)





async def did_not_understand_message(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("did_not_understand", {}, llm=llm)





async def greeting_message(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("greeting", {}, llm=llm)


async def start_welcome_message(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("start_welcome", {}, llm=llm, temperature=0.65)


async def off_topic_message(
    *,
    services: list[str],
    step: str = "",
    user_text: str = "",
    llm: LLMClient | None = None,
) -> str:
    from services.copy_variants import format_services_catalog
    from services.service_grammar import service_accusative

    catalog = format_services_catalog([service_accusative(s) for s in services])
    facts: dict[str, str] = {"services": catalog or "услуги салона"}
    if step:
        facts["step"] = step
    return await human_reply.say(
        "off_topic",
        facts,
        user_text=user_text,
        llm=llm,
        temperature=0.72,
    )


async def free_chat_message(
    *,
    services: list[str],
    user_text: str,
    step: str = "",
    llm: LLMClient | None = None,
) -> str:
    """Свободный диалог: короткий человеческий ответ + мягкий возврат к записи."""
    from services.copy_variants import format_services_catalog
    from services.service_grammar import service_accusative

    catalog = format_services_catalog([service_accusative(s) for s in services])
    facts: dict[str, str] = {"services": catalog or "услуги салона"}
    if step:
        facts["step"] = step
    return await human_reply.say(
        "free_chat",
        facts,
        user_text=user_text,
        llm=llm,
        temperature=0.7,
    )





async def welcome_with_catalog(
    services: list[str], *, user_text: str = "", llm: LLMClient | None = None,
) -> str:
    from services.copy_variants import format_services_catalog
    from services.service_grammar import service_accusative

    labels = [service_accusative(s) for s in services]
    catalog = format_services_catalog(labels)
    return await human_reply.say(
        "welcome",
        {"services": catalog},
        user_text=user_text,
        llm=llm,
    )





async def help_text(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("help", {}, llm=llm)





async def name_prompt(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("enter_name", {}, llm=llm)





async def name_length_error(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("name_invalid", {}, llm=llm)





async def phone_after_name(*, first_name: str = "", llm: LLMClient | None = None) -> str:
    facts: dict[str, str] = {}
    if first_name.strip():
        facts["first_name"] = first_name.strip()
    return await human_reply.say("enter_phone", facts, llm=llm)





async def phone_invalid_error(*, attempt: int = 0, llm: LLMClient | None = None) -> str:
    return await human_reply.say("phone_invalid", {"attempt": attempt + 1}, llm=llm)





async def phone_not_now_hint(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("phone_not_now", {}, llm=llm)





async def confirm_intro(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("confirm_intro", {}, llm=llm, temperature=0.55)





async def booking_created(
    when_str: str, master_name: str = "", *, llm: LLMClient | None = None,
) -> str:
    from services.copy_variants import master_dative

    facts: dict[str, str] = {"when": when_str}
    if master_name:
        facts["master"] = master_name
        facts["master_dative"] = master_dative(master_name)
    msg = await human_reply.say(
        "booking_created", facts, llm=llm, temperature=0.55,
    )
    if when_str in msg and not human_reply.booking_phrase_broken(msg):
        return msg
    return human_reply._example_fallback("booking_created", facts)





async def booking_ready_intro(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("booking_ready_intro", {}, llm=llm)





async def booking_cancelled(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("booking_cancelled", {}, llm=llm, temperature=0.55)





async def booking_cancelled_detail(
    service_name: str, master_name: str, when: str, *, llm: LLMClient | None = None,
) -> str:
    from services.copy_variants import master_dative
    from services.service_grammar import service_accusative, service_speech_label

    facts = {
        "service": service_speech_label(service_name),
        "service_acc": service_accusative(service_name),
        "master": master_name,
        "master_dative": master_dative(master_name),
        "when": when,
    }
    msg = await human_reply.say(
        "booking_cancelled_detail", facts, llm=llm, temperature=0.55,
    )
    if when in msg and not human_reply.booking_phrase_broken(msg):
        return msg
    return human_reply._example_fallback("booking_cancelled_detail", facts)





async def cancel_which_booking_prompt(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("cancel_which", {}, llm=llm)





async def cancel_all_confirm_prompt(count: int, *, llm: LLMClient | None = None) -> str:

    return await human_reply.say("cancel_all_confirm", {"count": count}, llm=llm)





async def cancel_all_done(count: int, *, llm: LLMClient | None = None) -> str:

    return await human_reply.say("cancel_all_done", {"count": count}, llm=llm)





async def cancel_booking_not_found_hint(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("cancel_not_found", {}, llm=llm)


async def leave_bookings_message(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("leave_bookings", {}, llm=llm)





async def step_cancelled(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("step_cancelled", {}, llm=llm)





async def unsupported_service_message(

    requested: str,

    available: list[str],

    *,

    quoted: bool = False,

    user_text: str = "",

    llm: LLMClient | None = None,

) -> str:

    from services.service_grammar import service_accusative



    opts = ", ".join(service_accusative(a) for a in available[:3]) if available else ""

    return await human_reply.say(

        "unsupported_service",

        {"requested": requested, "options": opts, "quoted": quoted},

        user_text=user_text,

        llm=llm,

    )





async def returning_booking_ack(

    first_name: str | None = None, *, llm: LLMClient | None = None,

) -> str:

    return await human_reply.say("returning_ack", {"first_name": first_name or ""}, llm=llm)





async def service_choice_prompt(options: list[str], *, llm: LLMClient | None = None) -> str:
    from services.copy_variants import format_services_catalog
    from services.service_grammar import service_accusative

    labels = [service_accusative(o) for o in options]
    catalog = format_services_catalog(labels)
    return await human_reply.say("service_choice", {"options": catalog}, llm=llm)





async def later_slots_unavailable(latest: str, *, llm: LLMClient | None = None) -> str:

    return await human_reply.say("later_slots", {"latest": latest, "requested": "позже"}, llm=llm)





async def waitlist_not_available_yet(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("waitlist", {}, llm=llm)





async def date_corrected_ack(date_label: str, *, llm: LLMClient | None = None) -> str:

    return await human_reply.say("date_corrected", {"date_label": date_label}, llm=llm)





async def invalid_master_for_service(
    master_name: str, service_name: str, alternatives: list[str], *, llm: LLMClient | None = None,
) -> str:
    from services.service_grammar import service_accusative

    return await human_reply.say(
        "invalid_master",
        {
            "master": master_name,
            "service": service_accusative(service_name),
            "alternatives": ", ".join(alternatives),
        },
        llm=llm,
    )





async def alternative_slot_prompt(

    requested: str, offered: str, delta_min: int, *, llm: LLMClient | None = None,

) -> str:

    return await human_reply.say(

        "alternative_slot",

        {"requested": requested, "offered": offered, "delta_min": delta_min},

        llm=llm,

    )





async def complaint_recovery_message(

    *, promo: str = "", admin_contact: str = "", llm: LLMClient | None = None,

) -> str:

    return await human_reply.say(

        "complaint_recovery",

        {"promo": promo, "admin_contact": admin_contact},

        llm=llm,

    )





async def feedback_thanks(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("feedback_thanks", {}, llm=llm)





async def reschedule_done(

    service_name: str, master_name: str, when: str, *, llm: LLMClient | None = None,

) -> str:

    body = fmt_booking_summary(service_name, master_name, when)

    intro = await human_reply.say(

        "reschedule_done",

        {"service": service_name, "master": master_name, "when": when},

        llm=llm,

    )

    return f"{intro}\n\n{body}"





async def faq_answer(text: str, *, llm: LLMClient | None = None) -> str | None:

    if not looks_like_faq_request(text):

        return None

    s = get_settings()

    low = text.lower()

    if _PET_FAQ_RE.search(low):

        return await human_reply.say(

            "faq_pets",

            {"pets_allowed": s.pets_allowed},

            user_text=text,

            llm=llm,

        )

    if any(w in low for w in ("лак", "бренд", "фирм")):

        return await human_reply.say("faq_brands", {"brands": s.salon_brands.strip()}, user_text=text, llm=llm)

    if "френч" in low:

        return await human_reply.say("faq_french", {}, user_text=text, llm=llm)

    return None





def booking_short_line(service_name: str, duration_min: int, price_rub: int) -> str:
    from services.service_grammar import service_speech_label

    return f"💅 {service_speech_label(service_name)} · {duration_min} мин · {price_rub} ₽"





async def choose_master_prompt(*, llm: LLMClient | None = None) -> str:
    return await human_reply.say("choose_master", {}, llm=llm)


async def choose_date_prompt(master_name: str, *, llm: LLMClient | None = None) -> str:
    from services.copy_variants import master_dative

    return await human_reply.say(
        "choose_date",
        {"master": master_dative(master_name)},
        llm=llm,
    )





async def choose_slot_prompt(
    master_name: str,
    date_str: str,
    *,
    times: list[str] | None = None,
    llm: LLMClient | None = None,
) -> str:
    from services.copy_variants import master_genitive

    if times:
        from services.copy_variants import master_dative

        return await human_reply.say(
            "choose_slot_times",
            {
                "master": master_name,
                "master_dative": master_dative(master_name),
                "date": date_str,
                "times": ", ".join(times),
            },
            llm=llm,
        )

    return await human_reply.say(
        "choose_slot",
        {"master": master_name, "master_genitive": master_genitive(master_name), "date": date_str},
        llm=llm,
    )





async def no_slots_prompt(master_name: str, *, llm: LLMClient | None = None) -> str:

    return await human_reply.say("no_slots", {"master": master_name}, llm=llm)





async def masters_list_intro(*, llm: LLMClient | None = None) -> str:

    return await human_reply.say("masters_intro", {}, llm=llm)





def master_card_line(name: str, service_names: str) -> str:

    return f"• <b>{name}</b> — {service_names}"





async def availability_intro(

    master_name: str, date_label: str | None = None, *, llm: LLMClient | None = None,

) -> str:

    if date_label:

        return await choose_slot_prompt(master_name, date_label, llm=llm)

    return await choose_date_prompt(master_name, llm=llm)





def cancel_booking_button_label(when: str) -> str:

    return f"❌ Отменить · {when}"





async def multi_booking_plan(

    lines: list[tuple[str, str]], *, llm: LLMClient | None = None,

) -> str:

    plan = "; ".join(f"{i}. {svc} — {when}" for i, (svc, when) in enumerate(lines, 1))

    intro = await human_reply.say("multi_booking_plan", {"plan": plan}, llm=llm)

    detail = "\n".join(f"{i}. {svc} — {when}" for i, (svc, when) in enumerate(lines, 1))

    return f"{intro}\n\n{detail}"





async def multi_booking_continue(

    service_name: str, date_label: str, *, llm: LLMClient | None = None,

) -> str:

    return await human_reply.say(

        "multi_booking_continue",

        {"service_name": service_name, "date_label": date_label},

        llm=llm,

    )


