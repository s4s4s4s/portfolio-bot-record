"""Вариативные фразы и склонение имён мастеров (грамматика, не тексты бота)."""



from __future__ import annotations



from services import human_reply





def format_services_catalog(labels: list[str]) -> str:

    """«маникюр, массаж или стрижку» — без нумерованных списков."""

    clean = [x for x in labels if x]

    if not clean:

        return ""

    if len(clean) == 1:

        return clean[0]

    if len(clean) == 2:

        return f"{clean[0]} или {clean[1]}"

    return ", ".join(clean[:-1]) + f" или {clean[-1]}"





async def pick_welcome_message(catalog: str) -> str:

    return await human_reply.say("welcome", {"services": catalog or "услуги салона"})





async def pick_confirm_intro() -> str:

    return await human_reply.say("confirm_intro", {}, temperature=0.55)





async def pick_step_cancelled() -> str:

    return await human_reply.say("step_cancelled", {})





async def pick_choose_master_prompt() -> str:

    return await human_reply.say("choose_master", {})





async def pick_choose_date_prompt(master_dative: str) -> str:

    return await human_reply.say("choose_date", {"master": master_dative})





async def pick_enter_name_prompt() -> str:

    return await human_reply.say("enter_name", {})





async def pick_enter_phone_prompt(*, first_name: str = "") -> str:

    facts: dict[str, str] = {}

    if first_name.strip():

        facts["first_name"] = first_name.strip()

    return await human_reply.say("enter_phone", facts)





async def pick_slot_then_name_prompt(time_label: str) -> str:

    return await human_reply.say("slot_time_ack", {"time": time_label})





async def pick_name_invalid_prompt() -> str:

    return await human_reply.say("name_invalid", {})





async def pick_phone_invalid_prompt() -> str:

    return await human_reply.say("phone_invalid", {})





def master_is_feminine(name: str) -> bool:



    stem = (name or "").strip().split()[0]



    low = stem.lower()



    if low.endswith(("ий", "ей", "ай", "ел", "им", "ур", "ан", "он", "ил")):



        return False



    return low.endswith(("а", "я"))











def master_genitive(name: str) -> str:



    """Родительный для «у Анны», «у Дмитрия»."""



    stem = (name or "").strip().split()[0]



    low = stem.lower()



    if low.endswith("ий"):



        return stem[:-2] + "ия"



    if low.endswith("й") and not low.endswith("ий"):



        return stem[:-1] + "я"



    if low.endswith("а"):



        return stem[:-1] + "ы"



    if low.endswith("я"):



        return stem[:-1] + "и"



    return stem











def master_dative(name: str) -> str:

    """Дательный для «к Дмитрию», «к Анне»."""

    stem = (name or "").strip().split()[0]

    low = stem.lower()

    if low.endswith("ий"):

        return stem[:-2] + "ию"

    if low.endswith("й") and not low.endswith("ий"):

        return stem[:-1] + "ю"

    if low.endswith("а"):

        return stem[:-1] + "е"

    if low.endswith("я"):

        return stem[:-1] + "е"

    return stem











async def date_step_nudge(*, llm=None) -> str:



    return await human_reply.say("date_step_nudge", {}, llm=llm)











async def slot_step_nudge(*, llm=None) -> str:



    return await human_reply.say("slot_step_nudge", {}, llm=llm)





