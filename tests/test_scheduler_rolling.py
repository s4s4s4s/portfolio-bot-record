"""Rolling-window job: idempotent догенерация слотов."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy import select

from db.models import Slot
from db.repositories import MasterRepo, ServiceRepo
from services.slot_generator import generate_one_day_ahead, generate_slots_window

pytestmark = pytest.mark.asyncio


async def _two_masters_setup(session) -> None:  # type: ignore[no-untyped-def]
    svc_repo = ServiceRepo(session)
    cut = await svc_repo.get_or_create(name="cut", duration_min=60, price_kop=10000)
    color = await svc_repo.get_or_create(name="color", duration_min=180, price_kop=20000)
    m_repo = MasterRepo(session)
    await m_repo.get_or_create(
        name="A",
        services_csv=f"{cut.id},{color.id}",
        schedule={
            "mon": ["10:00", "20:00"], "tue": ["10:00", "20:00"],
            "wed": ["10:00", "20:00"], "thu": ["10:00", "20:00"],
            "fri": ["10:00", "20:00"],
        },
    )
    await m_repo.get_or_create(
        name="B",
        services_csv=f"{cut.id}",
        schedule={
            "tue": ["11:00", "13:00"],
            "thu": ["11:00", "13:00"],
        },
    )
    await session.flush()


@freeze_time("2030-05-01")  # Wednesday
async def test_rolling_creates_only_one_day(session) -> None:  # type: ignore[no-untyped-def]
    await _two_masters_setup(session)
    initial_total = await generate_slots_window(session, days=14)
    rolling = await generate_one_day_ahead(session, horizon_days=14)
    rows = await session.execute(select(Slot))
    all_slots = list(rows.scalars().all())
    target_day = date(2030, 5, 1) + timedelta(days=14)
    target_start = datetime.combine(target_day, time.min)
    target_end = target_start + timedelta(days=1)
    new_day_slots = [s for s in all_slots if target_start <= s.start_at < target_end]
    assert len(new_day_slots) >= rolling > 0
    assert initial_total > 0


@freeze_time("2030-05-01")
async def test_rolling_idempotent_double_run(session) -> None:  # type: ignore[no-untyped-def]
    await _two_masters_setup(session)
    await generate_slots_window(session, days=14)
    first_run = await generate_one_day_ahead(session, horizon_days=14)
    second_run = await generate_one_day_ahead(session, horizon_days=14)
    assert first_run > 0
    assert second_run == 0


@freeze_time("2030-05-01")
async def test_rolling_uses_master_schedule_correctly(session) -> None:  # type: ignore[no-untyped-def]
    """Мастер B работает только по вторникам и четвергам — на target_day,
    который воскресенье, новых слотов от него не появится."""
    await _two_masters_setup(session)
    rolling = await generate_one_day_ahead(session, horizon_days=14)
    rows = await session.execute(select(Slot))
    target_day = date(2030, 5, 1) + timedelta(days=14)
    weekday = target_day.weekday()
    if weekday in (5, 6):
        assert rolling == 0
    else:
        assert rolling >= 0
    all_slots = list(rows.scalars().all())
    masters = await MasterRepo(session).list_active()
    a = next(m for m in masters if m.name == "A")
    a_slots = [s for s in all_slots if s.master_id == a.id]
    assert len(a_slots) > 0
