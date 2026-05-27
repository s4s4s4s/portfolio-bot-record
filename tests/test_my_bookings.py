"""Тесты /my-функционала: показ активных, отмена, изоляция между клиентами."""
from __future__ import annotations

from datetime import datetime

import pytest

from db.repositories import BookingRepo, ClientRepo, MasterRepo, ServiceRepo, SlotRepo

pytestmark = pytest.mark.asyncio


async def _make_booking(session, *, tg_user_id: int, when: datetime) -> int:  # type: ignore[no-untyped-def]
    svc = await ServiceRepo(session).get_or_create(name="x", duration_min=30, price_kop=10000)
    m = await MasterRepo(session).get_or_create(
        name="m", services_csv=f"{svc.id}", schedule={"mon": ["10:00", "11:00"]},
    )
    slot = await SlotRepo(session).create_available(
        master_id=m.id, service_id=svc.id, start_at=when, duration_min=30,
    )
    client = await ClientRepo(session).upsert(
        tg_user_id=tg_user_id, tg_username=None, full_name="N", phone="+79051234567",
    )
    reserved = await SlotRepo(session).reserve_atomic(slot.id)
    assert reserved is not None
    booking = await BookingRepo(session).create(slot_id=reserved.id, client_id=client.id)
    reserved.booking_id = booking.id
    await session.flush()
    return booking.id


async def test_my_shows_only_own_bookings(session) -> None:  # type: ignore[no-untyped-def]
    bid_a = await _make_booking(session, tg_user_id=100, when=datetime(2030, 6, 1, 10, 0))
    bid_b = await _make_booking(session, tg_user_id=200, when=datetime(2030, 6, 1, 11, 0))
    client_a = await ClientRepo(session).get_by_tg(100)
    client_b = await ClientRepo(session).get_by_tg(200)
    assert client_a is not None and client_b is not None
    a_list = await BookingRepo(session).list_active_for_client(client_a.id)
    b_list = await BookingRepo(session).list_active_for_client(client_b.id)
    assert [b.id for b in a_list] == [bid_a]
    assert [b.id for b in b_list] == [bid_b]


async def test_cancel_makes_slot_available_again(session) -> None:  # type: ignore[no-untyped-def]
    bid = await _make_booking(session, tg_user_id=300, when=datetime(2030, 6, 2, 12, 0))
    booking = await BookingRepo(session).get(bid)
    assert booking is not None
    slot_id_before = booking.slot_id
    await BookingRepo(session).cancel(booking, reason="user")
    await session.flush()
    slot_after = await SlotRepo(session).get(slot_id_before)
    assert slot_after is not None
    assert slot_after.status == "available"
    assert slot_after.booking_id is None


async def test_rebook_after_cancel(session) -> None:  # type: ignore[no-untyped-def]
    """Отменённая бронь не блокирует повторную запись на тот же слот."""
    bid = await _make_booking(session, tg_user_id=301, when=datetime(2030, 6, 4, 14, 0))
    booking = await BookingRepo(session).get(bid)
    assert booking is not None
    slot_id = booking.slot_id
    await BookingRepo(session).cancel(booking, reason="user")
    await session.flush()

    client = await ClientRepo(session).get_by_tg(301)
    assert client is not None
    reserved = await SlotRepo(session).reserve_atomic(slot_id)
    assert reserved is not None
    revived = await BookingRepo(session).create_active_for_slot(
        slot_id=slot_id, client_id=client.id,
    )
    assert revived.id == bid
    assert revived.status == "active"
    reserved.booking_id = revived.id
    await session.flush()

    actives = await BookingRepo(session).list_active_for_client(client.id)
    assert len(actives) == 1
    assert actives[0].slot_id == slot_id


async def test_cancel_excludes_from_my(session) -> None:  # type: ignore[no-untyped-def]
    bid = await _make_booking(session, tg_user_id=400, when=datetime(2030, 6, 3, 13, 0))
    booking = await BookingRepo(session).get(bid)
    assert booking is not None
    await BookingRepo(session).cancel(booking)
    await session.flush()
    client = await ClientRepo(session).get_by_tg(400)
    assert client is not None
    actives = await BookingRepo(session).list_active_for_client(client.id)
    assert actives == []
