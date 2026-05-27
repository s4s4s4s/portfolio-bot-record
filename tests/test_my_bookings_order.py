"""Порядок списка «Мои записи» — по дате визита."""
from __future__ import annotations

import pytest

from db.repositories import BookingRepo, ClientRepo, MasterRepo, ServiceRepo, SlotRepo

pytestmark = pytest.mark.asyncio

_HAIRCUT_NAME = "Стрижка (без окрашивания)"


async def test_list_active_for_client_order_by_visit_date(session_with_seed: object) -> None:
    session = session_with_seed  # type: ignore[assignment]
    client = await ClientRepo(session).upsert(  # type: ignore[arg-type]
        tg_user_id=999001,
        tg_username="tester",
        full_name="Тест",
        phone="+79051111111",
    )
    services = await ServiceRepo(session).list_active()  # type: ignore[arg-type]
    haircut = next(x for x in services if x.name == _HAIRCUT_NAME)
    master = (await MasterRepo(session).list_for_service(haircut.id))[0]  # type: ignore[arg-type]
    dates = await SlotRepo(session).list_available_dates(master.id, days=14)  # type: ignore[arg-type]
    slots: list = []
    for d in dates:
        day_slots = await SlotRepo(session).list_available_on_date(master.id, d, haircut.id)  # type: ignore[arg-type]
        if len(day_slots) >= 2:
            slots = day_slots
            break
    assert len(slots) >= 2, "need 2 free slots on one day"
    slots_sorted = sorted(slots, key=lambda s: s.start_at)
    repo = BookingRepo(session)  # type: ignore[arg-type]
    await repo.create(slot_id=slots_sorted[1].id, client_id=client.id)
    await repo.create(slot_id=slots_sorted[0].id, client_id=client.id)
    listed = await repo.list_active_for_client(client.id)
    assert len(listed) >= 2
    times = [b.slot.start_at for b in listed if b.slot]
    assert times == sorted(times)
