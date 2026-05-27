"""Прошедшие даты и время не показываются и не бронируются."""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from db.repositories import MasterRepo, ServiceRepo, SlotRepo
from services.salon_time import is_past_date, is_past_slot, slot_query_from


def test_past_date_detected() -> None:
    assert is_past_date(date(2000, 1, 1)) is True


def test_slot_query_from_past_day_returns_none() -> None:
    now = datetime(2026, 5, 21, 15, 0)
    assert slot_query_from(date(2026, 5, 20), now=now) is None


def test_slot_query_from_today_uses_now() -> None:
    now = datetime(2026, 5, 21, 15, 0)
    assert slot_query_from(date(2026, 5, 21), now=now) == now


def test_slot_query_from_future_day_starts_at_midnight() -> None:
    now = datetime(2026, 5, 21, 15, 0)
    assert slot_query_from(date(2026, 5, 22), now=now) == datetime(2026, 5, 22, 0, 0)


def test_is_past_slot_with_reference_now() -> None:
    now = datetime(2026, 5, 21, 15, 0)
    assert is_past_slot(datetime(2026, 5, 21, 14, 0), now=now) is True
    assert is_past_slot(datetime(2026, 5, 21, 15, 0), now=now) is False


@pytest.mark.asyncio
async def test_list_available_on_date_skips_past_times_today(session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fixed_now = datetime(2026, 5, 21, 15, 0)

    def _fake_now() -> datetime:
        return fixed_now

    monkeypatch.setattr("db.repositories.slot.salon_now_naive", _fake_now)
    monkeypatch.setattr("services.salon_time.salon_now_naive", _fake_now)

    svc = await ServiceRepo(session).get_or_create(name="t", duration_min=30, price_kop=10000)
    m = await MasterRepo(session).get_or_create(
        name="m", services_csv=f"{svc.id}", schedule={"mon": ["10:00", "20:00"]},
    )
    repo = SlotRepo(session)
    early = await repo.create_available(
        master_id=m.id, service_id=svc.id,
        start_at=datetime.combine(date(2026, 5, 21), time(10, 0)),
        duration_min=30,
    )
    late = await repo.create_available(
        master_id=m.id, service_id=svc.id,
        start_at=datetime.combine(date(2026, 5, 21), time(16, 0)),
        duration_min=30,
    )
    await session.flush()

    slots = await repo.list_available_on_date(m.id, date(2026, 5, 21), svc.id)
    ids = {s.id for s in slots}
    assert early.id not in ids
    assert late.id in ids
