"""Дата в запросе → фильтр мастеров и подсказка альтернатив (тексты через LLM)."""
from __future__ import annotations

from datetime import date

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.client import masters_kb, slots_kb
from bot.states import BookingStates
from db.models import Master, Service
from db.repositories import MasterRepo, SlotRepo
from services import human_reply
from services.booking_hints import format_date_user_label
from services.copy_variants import master_genitive
from services.llm_client import LLMClient, get_llm_client
from services.period_offer import master_informal_at
from services.persona import booking_short_line, choose_slot_prompt


async def collect_masters_on_date(
    session: AsyncSession,
    *,
    service_id: int,
    target: date,
    exclude_master_id: int | None = None,
) -> list[Master]:
    slot_repo = SlotRepo(session)
    master_repo = MasterRepo(session)
    found: list[Master] = []
    for master in await master_repo.list_for_service(service_id):
        if exclude_master_id is not None and master.id == exclude_master_id:
            continue
        slots = await slot_repo.list_available_on_date(master.id, target, service_id)
        if slots:
            found.append(master)
    return found


async def say_date_master_intro(
    target: date,
    masters: list[Master],
    *,
    llm: LLMClient | None = None,
) -> str:
    label = format_date_user_label(target)
    if len(masters) == 1:
        return await human_reply.say(
            "date_master_intro_single",
            {"date_label": label, "master": masters[0].name},
            llm=llm,
        )
    names = ", ".join(m.name for m in masters)
    return await human_reply.say(
        "date_master_intro_multi",
        {"date_label": label, "masters": names},
        llm=llm,
    )


async def say_date_miss_one_alt(
    master_name: str,
    target: date,
    alt_name: str,
    *,
    llm: LLMClient | None = None,
) -> str:
    return await human_reply.say(
        "date_miss_one_alt",
        {
            "date_label": format_date_user_label(target),
            "master": master_name,
            "master_genitive": master_genitive(master_name),
            "alt": alt_name,
            "alt_genitive": master_informal_at(alt_name),
        },
        llm=llm,
    )


async def say_date_miss_many_alts(
    master_name: str,
    target: date,
    *,
    llm: LLMClient | None = None,
) -> str:
    return await human_reply.say(
        "date_miss_many_alts",
        {
            "date_label": format_date_user_label(target),
            "master": master_name,
            "master_genitive": master_genitive(master_name),
        },
        llm=llm,
    )


async def say_date_miss_no_alts(
    master_name: str,
    target: date,
    *,
    llm: LLMClient | None = None,
) -> str:
    return await human_reply.say(
        "date_miss_no_alts",
        {
            "date_label": format_date_user_label(target),
            "master": master_name,
            "master_genitive": master_genitive(master_name),
        },
        llm=llm,
    )


async def try_start_date_master_shortcut(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    service: Service,
    target: date,
) -> bool:
    """Если клиент назвал день — показываем только мастеров с окнами в этот день."""
    masters_for_svc = await MasterRepo(session).list_for_service(service.id)
    if len(masters_for_svc) <= 1:
        return False

    on_date = await collect_masters_on_date(
        session, service_id=service.id, target=target,
    )
    if not on_date or len(on_date) == len(masters_for_svc):
        return False

    price = service.price_kop // 100
    await state.update_data(
        service_id=service.id,
        target_date=target.isoformat(),
    )

    if len(on_date) == 1:
        master = on_date[0]
        await state.update_data(master_id=master.id)
        from bot.handlers.nlu import _show_availability

        await message.answer(booking_short_line(service.name, service.duration_min, price))
        await _show_availability(
            message, state, session, service, master, target.isoformat(), "", get_llm_client(),
        )
        return True

    await state.set_state(BookingStates.choosing_master)
    await message.answer(booking_short_line(service.name, service.duration_min, price))
    await message.answer(
        await say_date_master_intro(target, on_date),
        reply_markup=masters_kb(on_date),
    )
    return True


async def try_alternate_masters_for_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    service: Service,
    master: Master,
    target: date,
) -> bool:
    """У выбранного мастера нет окон в день из контекста — предложить других."""
    alts = await collect_masters_on_date(
        session,
        service_id=service.id,
        target=target,
        exclude_master_id=master.id,
    )
    if not alts:
        return False

    await state.update_data(target_date=target.isoformat())

    if len(alts) == 1:
        alt = alts[0]
        slots = await SlotRepo(session).list_available_on_date(
            alt.id, target, service.id,
        )
        if not slots:
            return False
        await state.update_data(master_id=alt.id)
        await state.set_state(BookingStates.choosing_slot)
        date_label = target.strftime("%d.%m")
        times = [s.start_at.strftime("%H:%M") for s in slots]
        await message.answer(await say_date_miss_one_alt(master.name, target, alt.name))
        await message.answer(
            await choose_slot_prompt(alt.name, date_label, times=times),
            reply_markup=slots_kb(slots),
        )
        return True

    await state.set_state(BookingStates.choosing_master)
    await message.answer(
        await say_date_miss_many_alts(master.name, target),
        reply_markup=masters_kb(alts),
    )
    return True
