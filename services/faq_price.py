"""Вопросы о цене — ответ из каталога через LLM."""
from __future__ import annotationsimport refrom aiogram.fsm.context import FSMContextfrom sqlalchemy.ext.asyncio import AsyncSessionfrom db.models import Servicefrom db.repositories import ServiceRepofrom services import human_replyfrom services.nlu import _best_matchfrom services.service_aliases import normalize_service_hintfrom services.service_grammar import service_speech_label_PRICE_ASK_RE = re.compile(
    r"(сколько\s+(?:у\s+вас\s+)?(?:стоит|будет|выйдет)|"
    r"стоимость|"
    r"\bцен[аыуе]\b|"
    r"прайс|"
    r"по\s+чем|"
    r"сколько\s+денег|"
    r"за\s+сколько)",
    re.IGNORECASE,
)

_FOLLOWUP_RE = re.compile(
    r"^(?:"
    r"да|угу|ага|ок(?:ей)?|"
    r"давай(?:те)?|"
    r"запиш(?:и|ите|аться|усь)?|"
    r"хочу|"
    r"можно|"
    r"конечно|"
    r"please|"
    r"час(?:ик|а|)?|"
    r"\d+\s*(?:мин|час)"
    r")(?:[.!?…,\s]|$)",
    re.IGNORECASE,
)


def looks_like_price_question(text: str) -> bool:
    return bool(_PRICE_ASK_RE.search((text or "").strip()))


def looks_like_price_followup(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or len(raw) > 40:
        return False
    if looks_like_price_question(raw):
        return False
    low = raw.lower()
    if any(w in low for w in ("отмен", "стоп", "не надо", "не нужн")):
        return False
    if _FOLLOWUP_RE.match(raw):
        return True
    return any(w in low for w in ("запиш", "записать", "хочу на", "давай"))


def _resolve_service(text: str, services: list[Service]) -> Service | None:
    names = [s.name for s in services]
    hint = normalize_service_hint(text)
    for probe in (hint, text):
        if not probe:
            continue
        match = _best_match(probe, names)
        if match:
            return next(s for s in services if s.name == match)
    low = text.lower()
    for svc in services:
        stem = svc.name.split("(")[0].strip().lower()
        if len(stem) >= 4 and stem[:5] in low:
            return svc
    return None


def _format_price_line(service: Service) -> str:
    label = service_speech_label(service.name)
    price = service.price_kop // 100
    return f"• {label} — {service.duration_min} мин, {price} ₽"


async def format_price_reply(services: list[Service], *, target: Service | None) -> str:
    if target is not None:
        label = service_speech_label(target.name)
        price = target.price_kop // 100
        return await human_reply.say(
            "faq_price_one",
            {
                "service": label,
                "duration": str(target.duration_min),
                "price": str(price),
            },
            user_text="",
        )
    body = "\n".join(_format_price_line(s) for s in services)
    return await human_reply.say("faq_price_list", {"price_list": body})


async def try_answer_price(
    text: str,
    session: AsyncSession,
    state: FSMContext,
) -> str | None:
    if not looks_like_price_question(text):
        return None
    services = await ServiceRepo(session).list_active()
    if not services:
        return None
    target = _resolve_service(text, services)
    await state.update_data(
        pending_after_price_service_id=target.id if target else None,
    )
    return await format_price_reply(services, target=target)
