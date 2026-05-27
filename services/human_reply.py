"""Живые ответы через LLM: без заготовленных фраз, только сцена + фacts."""

from __future__ import annotations



import json

import re

from typing import Any



from core.logging import get_logger

from services.llm_client import LLMClient, get_llm_client

from services.text_guard import sanitize_bot_text



log = get_logger()



# SMM-администратор салона: единый голос бренда для всех сцен.

_PERSONA_SYSTEM = """\

Ты — администратор и SMM-менеджер салона красоты. Пишешь клиентам в Telegram от лица живого человека на ресепшене.



ГОЛОС БРЕНДА

• Тепло, уверенно, по-деловому — как администратор хорошего салона, не как робот и не «подружка».

• Вежливое «вы», «вам», «вас», «ваш» — только с маленькой буквы, как в живом чате. Запрещены «ты», «тебе», «твой».

• О себе — женский род: «записала», «рада», «подскажу», «отменила», «не поняла».

• Подтверждение записи: «Записала вас к Дмитрию на 29.05 Пт 11:00» — подлежащее «я», не «вас записала».

• Отмена записи: «Отменила запись к Дмитрию на маникюр — 29.05 Пт 11:00» — не «вас отменили», не пассив про клиента.

• О клиенте: «записаться», «вам удобно», «вы выбрали». Никогда «вам бы хотела» — это ошибка.

• Пример даты: «На какую дату записать к Дмитрию?» — не «когда тебе удобно».

• Выбор записи для отмены: «Какую запись отменить?» — не «На какую запись отменить?» (так не говорят).



ГРАММАТИКА И РЕЧЬ

• Имена мастеров: к Дмитрию, к Анне; у Анны, у Дмитрия (используй master_genitive из ДАННЫЕ если есть).

• Услуги из options уже в нужном падеже — не ломай.

• Каждое предложение грамотно закончено. Вопрос — со знаком «?».

• Не склеивай два предложения без знака препинания между ними.

• Без канцелярита, без «данный», «осуществить», «в рамках».

• Не повторяй одну фразу два раза подряд.



ФОРМАТ

• 1–2 коротких предложения, до 280 символов.

• Максимум 1 эмодзи (или без него). Слово beauty не использовать — «салон красоты».

• Факты из ДАННЫЕ (имена, даты, время, цены) — дословно, не выдумывай.

• В конце последнего предложения не ставь точку (запятая и «?» внутри — можно).

• Для help допустимы теги <b>...</b>.



ЗАПРЕЩЕНО

• Смешивать «ты» и «вы» в одном сообщении.

• Женский род про клиента («записалась» про мужчину без «Вы»).

• Фамилия клиента, лекции про формат телефона (+7/8/10 цифр).

• Пассив про клиента: «вас отменили», «вас записала», «вас записали», «вы отменены» — только актив от администратора: «отменила запись», «записала вас».

• Шаблонные робот-фразы вроде «нажмите подходящую кнопку ниже» без живой формулировки.


ПРИМЕР

• В запросе будет эталонная фраза ПРИМЕР для этой сцены.

• Повтори её структуру, тон и длину; подставь значения из ДАННЫЕ.

• Не обрывай фразы («выбрали наш» без продолжения), не склеивай предложения без знака препинания.


Ответь только текстом сообщения клиенту — без кавычек, пояснений и markdown."""



_SCENE_TASKS: dict[str, str] = {

    "welcome": "Приветствие + услуги из services одной фразой; БЕЗ нумерованного списка (1. 2. 3.)",

    "greeting": "Короткое приветствие и готовность помочь с записью",

    "help": "Как записаться / мои записи / отмена; два блока с <b>",

    "choose_service": "Предложите выбрать услугу — кнопки или текстом",

    "choose_master": "К какому мастеру записать — один короткий вопрос; без «принимает», без «свободного времени нет»",

    "choose_date": "На какую дату записать к master (дательный падеж); один вопрос",

    "choose_slot": "Предложите выбрать время: date и master из ДАННЫЕ",

    "enter_name": "Спросите имя (без фамилии) для записи",

    "name_invalid": "Мягко: имя от 2 до 60 символов",

    "enter_phone": "Поблагодарите и попросите номер телефона — без лекции про формат",

    "phone_invalid": "Попросите повторить номер — без +7/8/10 цифр",

    "phone_not_now": "Номер можно позже; отмена — «отмена»",

    "confirm_intro": "РОВНО 2–4 слова, как в живом чате. Примеры: «Всё верно?», «Подтверждаем?». Без «салон красоты», без «перед записью»",

    "booking_created": (
        "Подтверди запись от лица администратора (я, женский род). "
        "Используй master_dative и when из ДАННЫЕ дословно. "
        "Пример: «Записала вас к Дмитрию на 29.05 Пт 11:00». "
        "ЗАПРЕЩЕНО: «вас записала», «вас записали»"
    ),

    "booking_cancelled": "Коротко: запись отменена — от лица администратора (я отменила)",

    "booking_cancelled_detail": (
        "Сообщи об отмене от лица администратора (я). "
        "Используй master_dative, service_acc и when из ДАННЫЕ. "
        "Пример: «Отменила запись к Дмитрию на маникюр — 29.05 Пт 11:00». "
        "ЗАПРЕЩЕНО: «вас отменили», «вас отменила», пассив про клиента"
    ),

    "cancel_not_found": (
        "Запись по тексту не распознала — коротко попроси выбрать нужную кнопку ниже"
    ),

    "cancel_which": (
        "Спроси, какую из записей отменить — один короткий вопрос. "
        "Правильно: «Какую запись отменить?». "
        "ЗАПРЕЩЕНО: «На какую запись отменить?», «На какую из записей отменить?»"
    ),

    "step_cancelled": "Запись не оформляем — коротко, по-человечески; без слова «шаг»",

    "unsupported_service": "Услуги requested нет; предложите options; учтите user_message",

    "returning_ack": "Клиент возвращается; first_name если есть — «Рада снова видеть вас»",

    "service_choice": "На options записать?",

    "later_slots": "Позже нет; предложите latest или другой день",

    "waitlist": "Уведомлений об окнах пока нет — выберите из списка",

    "date_corrected": "Дата date_label — выберите время",

    "invalid_master": "master не делает service; alternatives",

    "alternative_slot": "На requested не вышло; offered (delta_min)",

    "complaint_recovery": "Извинение без давления; promo, admin_contact",

    "feedback_thanks": "Спасибо за обратную связь",

    "reschedule_done": "Перенос: service, master, when",

    "faq_pets": "Питомцы: pets_allowed",

    "faq_brands": "Лаки/бренды brands или ресепшен",

    "faq_french": "Что такое френч + запись",

    "did_not_understand": "Не поняла — услуга и день или «Записаться»",

    "redirect": "Такой вопрос — ресепшен; с записью помогу",

    "free_chat": (
        "Клиент спросил что угодно (не обязательно про салон). "
        "Ответь по-человечески, коротко и уместно. "
        "Если вопрос не про запись — в конце мягко предложи записать/помочь с записью, без канцелярита"
    ),

    "no_slots": "У master нет мест на этот день",

    "masters_intro": "Одна строка перед списком мастеров",

    "multi_booking_plan": "План plan по очереди",

    "multi_booking_continue": "Дальше service_name на date_label",

    "booking_ready_intro": "ваша запись — карточка ниже",

    "date_step_nudge": "День — кнопкой или «завтра»",

    "slot_step_nudge": "Время — кнопкой или текстом",

    "slot_time_ok": "Время time принято — имя",

    "fsm_cancelled": "Отменено — снова «Записаться»",

    "fsm_invalid_service": "Услуги нет в списке",

    "fsm_invalid_master": "Мастер не делает услугу",

    "fsm_no_slots": "На день мест нет",

    "confirm_pick_hint": "Подтвердите — кнопка или «да»",

    "cancel_pick_hint": "Отмена всех — «да» или кнопка",

    "leave_bookings": "Записи оставила без изменений",

    "slot_past": "Время прошло — другое",

    "booking_error": "Ошибка — начните запись заново",

    "voice_listening": "Слушаю голосовое",

    "voice_failed": "Не расслышала — текстом или голосом",

    "menu_hint": "Меню ниже",

    "fsm_type_hint": "Дата/время — кнопкой или текстом",

    "phone_not_understood": "Номер не разобрала — напишите ещё раз",

    "phone_saved": "Номер сохранила",

    "slot_just_taken": "Окно заняли — попробуйте другое",

    "change_master_no_slots": "У master нет окон на дату",

    "day_past": "День прошёл — другой",

    "no_dates": "Нет свободных дней",

    "booking_refused_ack": "Без давления — когда захотите, запишемся",

    "slot_time_ack": "Время принято — как к вам обращаться",

    "cancel_already_gone": "Запись уже отменена",

    "confirm_cancel_all_nudge": "Подтвердите отмену всех",

    "bookings_already_cancelled_alert": "Записи уже отменены",

    "no_services": "Услуги не настроены — администратор",

    "pick_service": "Выберите услугу",

    "no_user": "Не определила пользователя",

    "no_bookings_yet": "Записей пока нет",

    "no_active_bookings": "Активных записей нет",

    "date_master_intro_single": "На date_label свободен только master — записываем?",

    "date_master_intro_multi": "На date_label могу записать к: masters",

    "date_miss_one_alt": (
        "У выбранного мастера нет окон на date_label; у alt_genitive есть — предложи посмотреть время. "
        "master_genitive и alt_genitive — родительный падеж (у Анны, у Димы)"
    ),

    "date_miss_many_alts": "На date_label у master_genitive мест нет — к кому из alternates записать?",

    "date_miss_no_alts": "На date_label у master_genitive мест нет — другой день",

    "period_master_offer": (
        "На date_phrase period_label окошка: offer_list. Спроси, к кому записать"
    ),

    "choose_slot_times": "На date к master_dative свободно: times — выбор времени",

    "faq_price_one": "Цена услуги service — duration мин, price ₽; предложи записать",

    "faq_price_list": "Прайс price_list; как записаться",

    "no_masters_for_service": "На service_acc нет мастеров — другая услуга",

    "session_expired": "Сессия устарела — снова «Записаться»",

    "master_no_slots_14d": "У master нет окон на 14 дней",

    "day_no_slots_alert": "На этот день мест нет",

    "invalid_master_alert": "master не делает service_acc; alternatives",

    "booking_session_gone": "Запись оформлена или сессия устарела",

    "start_welcome": "Приветствие + что бот помогает записаться; живой тон; кнопки меню",

    "off_topic": (
        "Клиент написал не про салон (провокация, пошлость, абсурд). "
        "Ответь по-человечески: лёгко, без морали и грубости, мягко верни к записи. "
        "Если step не пустой — напомни, на каком мы шаге. services — услуги салона"
    ),

    "booking_countdown": "Сколько осталось до визита — remaining, when, service, master_dative",

    "booking_countdown_multi": "Несколько записей — перечисли lines",

    "booking_countdown_none": "Нет активных записей — мягко предложи записаться",

}


# Эталонная фраза на сцену: LLM повторяет структуру и тон, подставляет ДАННЫЕ.
_SCENE_EXAMPLES: dict[str, str] = {
    "welcome": "Привет! Запишу вас на {services} — что выбираем?",
    "greeting": "Здравствуйте! Помогу с записью",
    "help": "<b>Запись</b>\nНапишите услугу или нажмите «Записаться»\n\n<b>Мои записи и отмена</b>\n«Мои записи» или «отменить запись»",
    "choose_service": "На какую услугу записать?",
    "choose_master": "К какому мастеру записать?",
    "choose_date": "На какую дату записать к {master}?",
    "choose_slot": "Выберите время на {date} у {master}",
    "enter_name": "Как к вам обращаться?",
    "name_invalid": "Не разобрала имя — напишите, как к вам обращаться",
    "enter_phone": "{first_name}, оставьте номер телефона для связи",
    "phone_invalid": "Не разобрала номер — напишите ещё раз",
    "phone_not_now": "Номер можно прислать позже — или «отмена», если передумали",
    "confirm_intro": "Всё верно?",
    "booking_created": "Записала вас к {master_dative} на {when}",
    "booking_cancelled": "Запись отменила",
    "booking_cancelled_detail": "Отменила запись к {master_dative} на {service_acc} — {when}",
    "cancel_not_found": "Такой записи нет — выберите нужную кнопкой ниже",
    "cancel_which": "Какую запись отменить?",
    "step_cancelled": "Хорошо, без записи",
    "unsupported_service": "К сожалению, {requested} не делаем — могу предложить {options}",
    "returning_ack": "Рада снова видеть вас, {first_name}!",
    "service_choice": "На маникюр, массаж или стрижку записать?",
    "later_slots": "Позже на этот день мест нет — ближайшее {latest}",
    "waitlist": "Уведомлений об окнах пока нет — выберите время из списка",
    "date_corrected": "На {date_label} — выберите время",
    "invalid_master": "{master} не делает {service} — могу предложить {alternatives}",
    "alternative_slot": "На {requested} не вышло — есть {offered}",
    "complaint_recovery": "Извините за неудобства — напишите администратору, с записью помогу",
    "feedback_thanks": "Спасибо за обратную связь!",
    "reschedule_done": "Перенесла: {service} к {master} на {when}",
    "faq_pets": "С питомцами {pets_allowed} — уточните на ресепшене",
    "faq_brands": "Работаем с {brands} — детали на ресепшене",
    "faq_french": "Френч — классический дизайн на кончиках — записать?",
    "did_not_understand": "Не поняла — напишите услугу и день или нажмите «Записаться»",
    "redirect": "Такой вопрос лучше на ресепшен — с записью помогу",
    "free_chat": "Поняла вас. Если хотите, могу помочь с записью — на какую услугу вас записать?",
    "no_slots": "У {master} на этот день мест нет",
    "masters_intro": "Наши мастера:",
    "multi_booking_plan": "Запишем по очереди: {plan}",
    "multi_booking_continue": "Дальше {service_name} на {date_label}",
    "booking_ready_intro": "Ваша запись — проверьте карточку ниже",
    "date_step_nudge": "Выберите день — кнопкой или «завтра»",
    "slot_step_nudge": "Выберите время — кнопкой или текстом",
    "slot_time_ok": "На {time} — отлично. Как к вам обращаться?",
    "fsm_cancelled": "Отменено — снова «Записаться»",
    "fsm_invalid_service": "Такой услуги нет в списке",
    "fsm_invalid_master": "Этот мастер не делает выбранную услугу",
    "fsm_no_slots": "На этот день мест нет",
    "confirm_pick_hint": "Подтвердите — кнопкой или «да»",
    "cancel_pick_hint": "Отменить все — «да» или кнопка",
    "leave_bookings": "Записи оставила без изменений",
    "slot_past": "Это время уже прошло — выберите другое",
    "booking_error": "Что-то пошло не так — начните запись заново через /start",
    "voice_listening": "Слушаю голосовое",
    "voice_failed": "Не расслышала — напишите текстом или ещё раз голосом",
    "menu_hint": "Меню ниже 👇",
    "fsm_type_hint": "Дату или время — кнопкой или текстом",
    "phone_not_understood": "Номер не разобрала — напишите ещё раз",
    "phone_saved": "Номер сохранила",
    "slot_just_taken": "Это окно только что заняли — попробуйте другое",
    "change_master_no_slots": "У {master} на {date} окон нет",
    "day_past": "Этот день уже прошёл — выберите другой",
    "no_dates": "Свободных дней пока нет — напишите администратору",
    "booking_refused_ack": "Хорошо — когда захотите, запишемся",
    "slot_time_ack": "На {time} — отлично. Как к вам обращаться?",
    "cancel_already_gone": "Эта запись уже отменена",
    "confirm_cancel_all_nudge": "Подтвердите отмену всех записей",
    "bookings_already_cancelled_alert": "Записи уже отменены",
    "no_services": "Услуги не настроены — напишите администратору",
    "pick_service": "Выберите услугу",
    "no_user": "Не определила пользователя",
    "no_bookings_yet": "Записей пока нет",
    "no_active_bookings": "Активных записей нет",
    "date_master_intro_single": "На {date_label} свободен только {master} — записываем?",
    "date_master_intro_multi": "На {date_label} могу записать к: {masters}",
    "date_miss_one_alt": "На {date_label} у {master_genitive} мест нет — у {alt_genitive} есть, смотрим время?",
    "date_miss_many_alts": "На {date_label} у {master_genitive} мест нет — к кому из них записать?",
    "date_miss_no_alts": "На {date_label} у {master_genitive} мест нет — выберите другой день",
    "period_master_offer": "На {date_phrase} {period_label} у нас {count} {windows_word}: {offer_list}. К кому записать?",
    "choose_slot_times": "На {date} к {master_dative} свободно: {times}. Выберите время 👇",
    "faq_price_one": "{service} — {duration} мин, {price} ₽. Записать?",
    "faq_price_list": "Наши цены:\n{price_list}\n\nНапишите услугу и день — или нажмите «Записаться»",
    "no_masters_for_service": "На {service_acc} пока нет мастеров — выберите другую услугу 👇",
    "session_expired": "Сессия устарела — нажмите «Записаться» и выберите время снова",
    "master_no_slots_14d": "У мастера нет свободных слотов в ближайшие 14 дней",
    "day_no_slots_alert": "На этот день уже нет свободных слотов",
    "invalid_master_alert": "{master} не выполняет {service_acc}. Доступные: {alternatives}",
    "booking_session_gone": "Запись уже оформлена или сессия устарела",
    "start_welcome": (
        "👋 Здравствуйте! Помогу записаться на услугу — "
        "можно писать как человеку или пользоваться кнопками ниже"
    ),
    "off_topic": "Ой, это не про салон 😊 Запишу на {services} — что выбираем?",

    "booking_countdown": "До записи на {service} к {master_dative} осталось {remaining} — {when}",

    "booking_countdown_multi": "Ваши ближайшие записи:\n{lines}",

    "booking_countdown_none": "Активных записей нет — когда захотите, запишемся",
}

_TY_RE = re.compile(r"\b(ты|тебе|твой|твоя|твоё|твои)\b", re.IGNORECASE)

_BROKEN_VAM_HOTELA = re.compile(

    r"вам\s+бы\s+хотела|хотела\s+бы\s+вам|вам\s+хотела",

    re.IGNORECASE,

)

_ROBOT_PHRASES = re.compile(

    r"перед\s+записью|в\s+наш\s+салон|салон\s+красоты|осуществить|данный",

    re.IGNORECASE,

)

_GHOST_NUMBER_LIST = re.compile(r"(?:\s+\d+\.)+\s*$")

_POLITE_CAP = re.compile(r"\b(Вы|Вам|Вас|Ваш|Ваша|Ваше|Ваши|Вами)\b")

_BROKEN_CLIENT_PASSIVE = re.compile(
    r"\bвас\s+(?:отменил|отменила|отменили|записал|записала|записали)\b",
    re.IGNORECASE,
)

_GRAMMAR_GUARD_SCENES = frozenset({
    "booking_created",
    "booking_cancelled",
    "booking_cancelled_detail",
})

_BROKEN_INCOMPLETE = re.compile(
    r"\b(?:выбрал(?:и)?|выбер(?:ите|и))\s+наш(?:\s|$)|"
    r"\bнаш\s+(?:можете|можно|скаж)|"
    r"на\s+какую\s+запись\s+отмен",
    re.IGNORECASE,
)

_EXAMPLE_GUARD_SCENES = frozenset({
    "enter_name",
    "enter_phone",
    "name_invalid",
    "phone_invalid",
    "slot_time_ack",
    "slot_time_ok",
})

_QUESTION_MARK_SCENES = frozenset({
    "enter_name",
    "name_invalid",
    "choose_master",
    "choose_date",
    "choose_slot",
    "choose_slot_times",
    "cancel_which",
    "slot_time_ack",
    "slot_time_ok",
    "date_master_intro_single",
    "date_miss_one_alt",
    "date_miss_many_alts",
    "period_master_offer",
    "faq_price_one",
})

_GRAMMAR_RETRY_HINT = (
    "\n(перепиши: только от лица администратора — «записала вас», «отменила запись»; "
    "запрещено «вас отменили», «вас записала»)"
)


def booking_phrase_broken(text: str) -> bool:
    return bool(_BROKEN_CLIENT_PASSIVE.search(text or ""))


def reply_phrase_broken(text: str, *, scene: str = "") -> bool:
    if booking_phrase_broken(text):
        return True
    if _BROKEN_INCOMPLETE.search(text or ""):
        return True
    if scene in _QUESTION_MARK_SCENES and text and "?" not in text and len(text) > 28:
        return True
    return False


def _fill_example(template: str, facts: dict[str, Any]) -> str:
    first_name = str(facts.get("first_name") or facts.get("name") or "").strip()
    if "{first_name}" in template and not first_name:
        if template.startswith("{first_name}"):
            out = "Оставьте номер телефона для связи"
        else:
            out = template
    else:
        out = template
    if first_name:
        out = out.replace("{first_name}", first_name)
    for key, val in facts.items():
        if key in ("first_name", "name") or val in (None, "", [], {}):
            continue
        if isinstance(val, list):
            text = ", ".join(str(x) for x in val)
        else:
            text = str(val)
        out = out.replace("{" + key + "}", text)
    out = re.sub(r"\{(\w+)\}", "", out)
    return re.sub(r"\s+", " ", out).strip(" ,—")


def _example_fallback(scene: str, facts: dict[str, Any]) -> str:
    template = _SCENE_EXAMPLES.get(scene)
    if not template:
        return _facts_line(facts)
    filled = _fill_example(template, facts)
    return _polish_smm(filled) if filled else _facts_line(facts)


def _polish_smm(text: str) -> str:

    """Мягкая пост-правка типичных косяков LLM."""

    out = text.strip()

    out = _TY_RE.sub("вам", out)

    out = _BROKEN_VAM_HOTELA.sub("вам удобно", out)

    if _ROBOT_PHRASES.search(out) and len(out) > 35:

        out = re.sub(_ROBOT_PHRASES, "", out).strip(" ,—")

    out = _GHOST_NUMBER_LIST.sub("", out)

    out = _POLITE_CAP.sub(lambda m: m.group(1).lower(), out)

    out = re.sub(
        r"\bвас\s+записала\b",
        "записала вас",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bвас\s+отменил(?:а|и)?\b",
        "отменила запись",
        out,
        flags=re.IGNORECASE,
    )

    out = re.sub(r"\s+", " ", out)

    out = re.sub(r"([а-яёa-z])([А-ЯЁ])", r"\1. \2", out)

    return out.strip()





def _facts_line(facts: dict[str, Any]) -> str:

    parts = [str(v) for v in facts.values() if v not in (None, "", [], {})]

    return ", ".join(parts) if parts else "—"





async def say(

    scene: str,

    facts: dict[str, Any] | None = None,

    *,

    user_text: str = "",

    llm: LLMClient | None = None,

    temperature: float = 0.35,

) -> str:

    """Сгенерировать ответ администратора. При сбое LLM — эталонный ПРИМЕР с подстановкой."""

    payload = dict(facts or {})

    task = _SCENE_TASKS.get(scene, "Ответь клиенту по контексту")

    example = _SCENE_EXAMPLES.get(scene)

    user_parts = [

        f"СЦЕНА: {scene}",

        f"ЗАДАЧА: {task}",

        f"ДАННЫЕ: {json.dumps(payload, ensure_ascii=False)}",

    ]

    if example:
        user_parts.append(
            f"ПРИМЕР: {_fill_example(example, payload)}",
        )

    if user_text.strip():

        user_parts.append(f"СООБЩЕНИЕ КЛИЕНТА: {user_text.strip()[:500]}")

    user_parts.append("Текст ответа:")



    client = llm or get_llm_client()

    def _accept(text: str) -> str:
        cleaned = sanitize_bot_text(_polish_smm(text.strip() if text else ""), fallback="")
        if not cleaned:
            return ""
        if scene in _GRAMMAR_GUARD_SCENES and booking_phrase_broken(cleaned):
            return ""
        if reply_phrase_broken(cleaned, scene=scene):
            return ""
        return cleaned

    raw = await client.chat(

        _PERSONA_SYSTEM,

        "\n".join(user_parts),

        temperature=temperature,

    )

    cleaned = _accept(raw or "")

    if cleaned:

        return cleaned



    log.warning("human_reply empty scene={scene}, retry", scene=scene)

    retry_suffix = _GRAMMAR_RETRY_HINT if scene in _GRAMMAR_GUARD_SCENES else (
        "\n(одно грамотное предложение по ПРИМЕРУ, «вы/вам/вас» с маленькой буквы)"
    )

    raw2 = await client.chat(

        _PERSONA_SYSTEM,

        "\n".join(user_parts) + retry_suffix,

        temperature=0.25,

    )

    cleaned2 = _accept(raw2 or "")

    if cleaned2:

        return cleaned2



    log.error("human_reply fallback to example scene={scene}", scene=scene)

    return _example_fallback(scene, payload)


