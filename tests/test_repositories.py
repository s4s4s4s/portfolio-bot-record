"""Базовые CRUD для репозиториев."""
from __future__ import annotations

from datetime import datetime

import pytest

from db.repositories import (
    AdminLogRepo,
    BookingRepo,
    ClientRepo,
    MasterRepo,
    ServiceRepo,
    SlotRepo,
)

pytestmark = pytest.mark.asyncio


async def test_service_get_or_create_idempotent(session) -> None:  # type: ignore[no-untyped-def]
    repo = ServiceRepo(session)
    a = await repo.get_or_create(name="Стрижка (без окрашивания)", duration_min=60, price_kop=150_000)
    b = await repo.get_or_create(name="Стрижка (без окрашивания)", duration_min=60, price_kop=150_000)
    assert a.id == b.id


async def test_master_list_for_service(session) -> None:  # type: ignore[no-untyped-def]
    svc_repo = ServiceRepo(session)
    s1 = await svc_repo.get_or_create(name="A", duration_min=30, price_kop=10000)
    s2 = await svc_repo.get_or_create(name="B", duration_min=30, price_kop=20000)
    m_repo = MasterRepo(session)
    m1 = await m_repo.get_or_create(name="M1", services_csv=f"{s1.id}", schedule={"mon": ["10:00", "11:00"]})
    m2 = await m_repo.get_or_create(name="M2", services_csv=f"{s1.id},{s2.id}", schedule={"mon": ["10:00", "11:00"]})
    masters_for_s1 = await m_repo.list_for_service(s1.id)
    assert {m.id for m in masters_for_s1} == {m1.id, m2.id}
    masters_for_s2 = await m_repo.list_for_service(s2.id)
    assert [m.id for m in masters_for_s2] == [m2.id]


async def test_client_upsert_updates_phone(session) -> None:  # type: ignore[no-untyped-def]
    repo = ClientRepo(session)
    c1 = await repo.upsert(tg_user_id=42, tg_username="x", full_name="A", phone="+79051111111")
    c2 = await repo.upsert(tg_user_id=42, tg_username="x", full_name="B", phone="+79052222222")
    assert c1.id == c2.id
    assert c2.phone == "+79052222222"
    assert c2.full_name == "B"


async def test_slot_create_and_atomic_reserve(session) -> None:  # type: ignore[no-untyped-def]
    svc = await ServiceRepo(session).get_or_create(name="x", duration_min=30, price_kop=10000)
    m = await MasterRepo(session).get_or_create(name="m", services_csv=f"{svc.id}", schedule={"mon": ["10:00", "11:00"]})
    repo = SlotRepo(session)
    when = datetime(2030, 5, 1, 10, 0)
    slot = await repo.create_available(master_id=m.id, service_id=svc.id, start_at=when, duration_min=30)
    reserved = await repo.reserve_atomic(slot.id)
    assert reserved is not None
    assert reserved.status == "booked"
    again = await repo.reserve_atomic(slot.id)
    assert again is None  # second attempt returns None


async def test_booking_create_and_cancel(session) -> None:  # type: ignore[no-untyped-def]
    svc = await ServiceRepo(session).get_or_create(name="x", duration_min=30, price_kop=10000)
    m = await MasterRepo(session).get_or_create(name="m", services_csv=f"{svc.id}", schedule={"mon": ["10:00", "11:00"]})
    slot = await SlotRepo(session).create_available(
        master_id=m.id, service_id=svc.id, start_at=datetime(2030, 5, 2, 11, 0), duration_min=30,
    )
    client = await ClientRepo(session).upsert(
        tg_user_id=99, tg_username=None, full_name="N", phone="+79051234567",
    )
    reserved = await SlotRepo(session).reserve_atomic(slot.id)
    assert reserved is not None
    booking = await BookingRepo(session).create(slot_id=reserved.id, client_id=client.id)
    reserved.booking_id = booking.id
    await session.flush()
    actives = await BookingRepo(session).list_active_for_client(client.id)
    assert len(actives) == 1
    assert actives[0].id == booking.id
    booked = await BookingRepo(session).get(booking.id)
    assert booked is not None
    await BookingRepo(session).cancel(booked, reason="test")
    await session.flush()
    actives_after = await BookingRepo(session).list_active_for_client(client.id)
    assert actives_after == []


async def test_admin_log_writes(session) -> None:  # type: ignore[no-untyped-def]
    repo = AdminLogRepo(session)
    entry = await repo.write(admin_tg_id=123, action="broadcast", payload={"to": 5})
    assert entry.id is not None
    assert entry.action == "broadcast"
    assert entry.payload_json is not None
