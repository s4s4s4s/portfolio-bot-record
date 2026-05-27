"""Тесты /today и /tomorrow — корректная фильтрация по дате."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from freezegun import freeze_time

from db.repositories import BookingRepo, ClientRepo, MasterRepo, ServiceRepo, SlotRepo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _align_salon_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """freezegun и salon TZ должны совпадать в тестах бронирования."""
    from datetime import datetime

    fixed = datetime(2030, 5, 1, 9, 0)

    def _now() -> datetime:
        return fixed

    monkeypatch.setattr("db.repositories.slot.salon_now_naive", _now)
    monkeypatch.setattr("services.salon_time.salon_now_naive", _now)


async def _seed_booking(session, *, when: datetime, tg_user_id: int) -> int:  # type: ignore[no-untyped-def]
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


@freeze_time("2030-05-01 09:00:00")
async def test_today_returns_only_today(session) -> None:  # type: ignore[no-untyped-def]
    today = date(2030, 5, 1)
    tomorrow = date(2030, 5, 2)
    bid_today = await _seed_booking(session, when=datetime(2030, 5, 1, 11, 0), tg_user_id=10)
    await _seed_booking(session, when=datetime(2030, 5, 2, 11, 0), tg_user_id=11)
    after = datetime.combine(today, time.min)
    before = after + timedelta(days=1)
    items = await BookingRepo(session).list_active_in_range(after=after, before=before)
    assert {b.id for b in items} == {bid_today}
    after_t = datetime.combine(tomorrow, time.min)
    before_t = after_t + timedelta(days=1)
    items_t = await BookingRepo(session).list_active_in_range(after=after_t, before=before_t)
    assert len(items_t) == 1
    assert items_t[0].id != bid_today


@freeze_time("2030-05-01 09:00:00")
async def test_excludes_cancelled_bookings(session) -> None:  # type: ignore[no-untyped-def]
    bid = await _seed_booking(session, when=datetime(2030, 5, 1, 12, 0), tg_user_id=20)
    booking = await BookingRepo(session).get(bid)
    assert booking is not None
    await BookingRepo(session).cancel(booking, reason="x")
    await session.flush()
    after = datetime.combine(date(2030, 5, 1), time.min)
    before = after + timedelta(days=1)
    items = await BookingRepo(session).list_active_in_range(after=after, before=before)
    assert items == []


@freeze_time("2030-05-01 09:00:00")
async def test_empty_day_returns_empty(session) -> None:  # type: ignore[no-untyped-def]
    after = datetime.combine(date(2030, 5, 1), time.min)
    before = after + timedelta(days=1)
    items = await BookingRepo(session).list_active_in_range(after=after, before=before)
    assert items == []


@freeze_time("2030-05-01 23:30:00")
async def test_late_night_today_still_includes_late_bookings(session) -> None:  # type: ignore[no-untyped-def]
    bid = await _seed_booking(session, when=datetime(2030, 5, 1, 23, 45), tg_user_id=30)
    after = datetime.combine(date(2030, 5, 1), time.min)
    before = after + timedelta(days=1)
    items = await BookingRepo(session).list_active_in_range(after=after, before=before)
    assert {b.id for b in items} == {bid}
