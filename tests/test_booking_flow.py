"""Booking flow: успех, race-condition, недоступный слот."""
from __future__ import annotations

import asyncio

import pytest

from db.repositories import (
    BookingRepo,
    ClientRepo,
    MasterRepo,
    ServiceRepo,
    SlotRepo,
)

pytestmark = pytest.mark.asyncio


async def test_booking_happy_path(session_with_seed) -> None:  # type: ignore[no-untyped-def]
    """Полная цепочка: услуга → мастер → слот → клиент → бронь.
    Проверяет что после reserve_atomic слот = booked и есть Booking."""
    s = session_with_seed
    services = await ServiceRepo(s).list_active()
    assert len(services) == 3
    haircut = next(x for x in services if "Стрижка" in x.name)
    masters = await MasterRepo(s).list_for_service(haircut.id)
    assert masters
    master = masters[0]
    dates = await SlotRepo(s).list_available_dates(master.id, days=14)
    assert dates, "ожидаются доступные даты"
    slots = await SlotRepo(s).list_available_on_date(master.id, dates[0], haircut.id)
    assert slots, "ожидаются доступные слоты"
    target_slot = slots[0]
    client = await ClientRepo(s).upsert(
        tg_user_id=12345, tg_username="t", full_name="Тест", phone="+79051234567",
    )
    reserved = await SlotRepo(s).reserve_atomic(target_slot.id)
    assert reserved is not None and reserved.status == "booked"
    booking = await BookingRepo(s).create(slot_id=reserved.id, client_id=client.id)
    reserved.booking_id = booking.id
    await s.flush()
    actives = await BookingRepo(s).list_active_for_client(client.id)
    assert len(actives) == 1
    assert actives[0].slot_id == target_slot.id


async def test_booking_slot_unavailable_after_reserve(session_with_seed) -> None:  # type: ignore[no-untyped-def]
    """После reserve_atomic второй вызов на тот же слот возвращает None."""
    s = session_with_seed
    services = await ServiceRepo(s).list_active()
    haircut = next(x for x in services if "Стрижка" in x.name)
    master = (await MasterRepo(s).list_for_service(haircut.id))[0]
    dates = await SlotRepo(s).list_available_dates(master.id, days=14)
    slots = await SlotRepo(s).list_available_on_date(master.id, dates[0], haircut.id)
    target = slots[0]
    a = await SlotRepo(s).reserve_atomic(target.id)
    b = await SlotRepo(s).reserve_atomic(target.id)
    assert a is not None
    assert b is None


async def test_booking_blocks_unavailable_dates(session_with_seed) -> None:  # type: ignore[no-untyped-def]
    """list_available_dates не показывает мастера в дни, где у него нет слотов
    по расписанию. Анна не работает по выходным — субботы/воскресенья
    в её доступных датах быть не должно."""
    s = session_with_seed
    masters = await MasterRepo(s).list_active()
    anna = next(m for m in masters if m.name == "Анна")
    dates = await SlotRepo(s).list_available_dates(anna.id, days=14)
    weekdays = {d.weekday() for d in dates}
    # 5 = sat, 6 = sun
    assert 5 not in weekdays
    assert 6 not in weekdays


async def test_booking_two_concurrent_reserve_only_one_wins(session_with_seed) -> None:  # type: ignore[no-untyped-def]
    """Стресс-сценарий: две параллельные reserve_atomic — выигрывает одна.

    SQLite в in-memory режиме не даёт реального параллелизма, но
    операции проходят последовательно — поэтому проверяем семантику
    «вторая вернёт None».
    """
    s = session_with_seed
    services = await ServiceRepo(s).list_active()
    haircut = next(x for x in services if "Стрижка" in x.name)
    master = (await MasterRepo(s).list_for_service(haircut.id))[0]
    dates = await SlotRepo(s).list_available_dates(master.id, days=14)
    slots = await SlotRepo(s).list_available_on_date(master.id, dates[0], haircut.id)
    slot_id = slots[0].id
    repo = SlotRepo(s)
    results = await asyncio.gather(repo.reserve_atomic(slot_id), repo.reserve_atomic(slot_id))
    successful = [r for r in results if r is not None]
    assert len(successful) == 1
