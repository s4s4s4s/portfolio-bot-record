"""NLU-слой: классификация intent + LLM-фразы FSM."""

from __future__ import annotations



import json

from dataclasses import dataclass

from datetime import date, datetime

from typing import Any



from core.logging import get_logger

from services import human_reply

from services.llm_client import LLMClient

from services.salon_time import salon_today

from services.text_guard import sanitize_bot_text



log = get_logger()



_INTENT_SYSTEM = (

    "Ты NLU-модуль записи в салон красоты. Ответь СТРОГО JSON без Markdown.\n"

    "Формат:\n"

    '{"intent":"...","entities":{"service_name":"...","master_name":"...","date_hint":"...","time_hint":"..."}}\n'

    'intents: "book" (запись или когда свободен мастер/слоты), "cancel" (отменить шаг/запись), '

    '"help", "my" (мои записи), "masters" (кто работает, без даты), "smalltalk" (привет), "other".\n'

    "Вопросы «когда свободен Дмитрий», «есть окна завтра» → intent book + master_name + date_hint.\n"

    "Если услуги нет в списке «Услуги в салоне» — верни service_name как написал пользователь, "

    "не подставляй другую услугу.\n"

)



_INTENT_EXAMPLE = (

    "Примеры:\n"

    'Ввод: "Хочу на стрижку к Анне на завтра в 14:00"\n'

    'Ответ: {"intent":"book","entities":{"service_name":"стрижка","master_name":"Анна","date_hint":"завтра","time_hint":"14:00"}}\n'

    'Ввод: "Хочу записаться на мелирование"\n'

    'Ответ: {"intent":"book","entities":{"service_name":"мелирование"}}\n'

    'Ввод: "Когда Дмитрий свободен завтра?"\n'

    'Ответ: {"intent":"book","entities":{"master_name":"Дмитрий","date_hint":"завтра"}}\n'

    'Ввод: "Запиши на френч завтра"\n'

    'Ответ: {"intent":"book","entities":{"service_name":"френч","date_hint":"завтра"}}\n'

    'Ввод: "Отменить" → {"intent":"cancel","entities":{}}\n'

    'Ввод: "Привет!" → {"intent":"smalltalk","entities":{}}\n'

)





@dataclass(frozen=True)

class NLUResult:

    intent: str

    entities: dict[str, str]

    reply_text: str

    keyboard: dict[str, Any] | None = None





async def classify_intent(

    user_text: str,

    llm: LLMClient,

    *,

    services: list[str] | None = None,

    masters: list[str] | None = None,

) -> dict[str, Any]:

    catalog = ""

    if services or masters:

        catalog = f"Услуги в салоне: {', '.join(services or [])}. Мастера: {', '.join(masters or [])}.\n"

    prompt = f"{_INTENT_EXAMPLE}\n{catalog}Теперь ввод:\n{user_text}\n"

    raw = await llm.chat(system=_INTENT_SYSTEM, user=prompt, temperature=0.0)

    if not raw or not raw.strip():

        log.warning("NLU classify returned empty, defaulting intent=other")

        return {"intent": "other", "entities": {}}



    cleaned = raw.strip()

    for fence in ("```json", "```"):

        cleaned = cleaned.replace(fence, "")

    cleaned = cleaned.strip()



    try:

        return json.loads(cleaned)

    except json.JSONDecodeError:

        log.warning("NLU classify JSON parsing failed, raw=%r", raw)

        return {"intent": "other", "entities": {}}





async def generate_greeting_reply(

    user_text: str,

    llm: LLMClient,

    *,

    services: list[str],

    masters: list[str],

) -> str:

    from services.persona import welcome_with_catalog



    _ = masters

    return await welcome_with_catalog(services, user_text=user_text, llm=llm)





async def generate_fsm_message(

    step: str,

    llm: LLMClient,

    service_name: str = "",

    master_name: str = "",

    price: int = 0,

    **extra: Any,

) -> str:

    scene = f"fsm_{step}" if step in {

        "cancelled", "invalid_service", "invalid_master", "no_slots",

    } else step

    facts: dict[str, Any] = {

        "service": service_name,

        "master": master_name,

        "price_rub": price,

        **extra,

    }

    return await human_reply.say(scene, facts, llm=llm)





async def generate_redirect_reply(user_text: str, llm: LLMClient) -> str:

    from services.persona import redirect_message



    return await redirect_message(user_text=user_text, llm=llm)





def _resolve_date(date_hint: str) -> date | None:

    if not date_hint:

        return None

    today = salon_today()

    low = date_hint.lower()

    resolved: date | None = None

    if "послепослезавтра" in low or "после послезавтра" in low:
        resolved = today + __import__("datetime", fromlist=["timedelta"]).timedelta(days=3)
    elif "послезавтра" in low:
        resolved = today + __import__("datetime", fromlist=["timedelta"]).timedelta(days=2)
    elif "завтра" in low:
        resolved = today + __import__("datetime", fromlist=["timedelta"]).timedelta(days=1)
    elif "сегодня" in low:
        resolved = today

    else:

        for fmt in ("%d.%m.%Y", "%d.%m"):

            try:

                resolved = datetime.strptime(low, fmt).date()

                break

            except ValueError:

                continue



        if resolved is None:

            import re

            m = re.search(

                r"(\d{1,2})\s+(число|мая|июня|июля|августа|сентября|октября|ноября|декабря|января|февраля|марта|апреля)",

                low,

            )

            if m:

                day = int(m.group(1))

                month_names = {

                    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,

                    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,

                }

                month = month_names.get(m.group(2), today.month)

                try:

                    resolved = date(today.year, month, day)

                except ValueError:

                    resolved = None



        if resolved is None:

            try:

                resolved = date.fromisoformat(low)

            except ValueError:

                return None



    if resolved is not None and resolved < today:

        return None

    return resolved





def _best_match(name: str, candidates: list[str]) -> str | None:

    if not name or not candidates:

        return None

    low = name.lower().strip()

    for c in candidates:

        if c.lower() == low:

            return c

    for c in candidates:

        if low in c.lower() or c.lower() in low:

            return c

    import difflib

    best_match = None

    best_ratio = 0.0

    for c in candidates:

        ratio = difflib.SequenceMatcher(None, low, c.lower()).ratio()

        if ratio > best_ratio and ratio >= 0.55:

            best_ratio = ratio

            best_match = c

    return best_match


