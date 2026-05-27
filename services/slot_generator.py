"""Генератор слотов для мастеров по их недельному расписанию.

Формат расписания мастера (Master.schedule_json):
  {"mon":["10:00","20:00"], "tue":["10:00","20:00"], ...}

Для каждой услуги из services_csv строится своя сетка с шагом duration_min;
слот не создаётся, если время пересекается с уже существующим слотом мастера
(один мастер — один приём в момент времени). Все слоты генерятся в UTC;
расписание в нижеследующем коде интерпретируется
как «локальное» время (читай: TZ владельца, переданное через ENV TZ).
Для демо-цели расхождение в пределах часа не критично; production —
переключаемо на `dateutil.tz` с реальной зоной.

Ключевые свойства:
  • idempotent: при повторной генерации существующие слоты пропускаются
    (защита через UNIQUE(master_id, start_at) на уровне БД и check внутри);
  • чистый: возвращает количество созданных слотов (без побочных I/O
    кроме db.session).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Master, Service
from db.repositories.master import MasterRepo
from db.repositories.slot import SlotRepo
from services.salon_time import salon_today

_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


async def generate_slots_for_day(
    session: AsyncSession,
    *,
    master: Master,
    target_date: date,
    services_by_id: dict[int, Service],
) -> int:
    """Генерит слоты для одного мастера на одну дату. Возвращает кол-во созданных."""
    schedule = MasterRepo.parse_schedule(master)
    weekday_key = _WEEKDAY_KEYS[target_date.weekday()]
    window = schedule.get(weekday_key)
    if not window or len(window) != 2:
        return 0
    try:
        h1, m1 = (int(x) for x in window[0].split(":"))
        h2, m2 = (int(x) for x in window[1].split(":"))
    except ValueError:
        return 0
    if (h2, m2) <= (h1, m1):
        return 0
    work_start = datetime.combine(target_date, time(h1, m1))
    work_end = datetime.combine(target_date, time(h2, m2))
    services_ids = [int(s.strip()) for s in master.services_csv.split(",") if s.strip().isdigit()]
    if not services_ids:
        return 0
    slot_repo = SlotRepo(session)
    created = 0
    for svc_id in services_ids:
        service = services_by_id.get(svc_id)
        if service is None:
            continue
        step = timedelta(minutes=service.duration_min)
        cursor = work_start
        while cursor + step <= work_end:
            existing = await slot_repo.find_by_master_service_start(
                master_id=master.id,
                service_id=service.id,
                start_at=cursor,
            )
            if existing is None:
                await slot_repo.create_available(
                    master_id=master.id,
                    service_id=service.id,
                    start_at=cursor,
                    duration_min=service.duration_min,
                )
                created += 1
            cursor += step
    return created


async def generate_slots_window(
    session: AsyncSession,
    *,
    days: int = 14,
    starting_from: date | None = None,
) -> int:
    """Генерит слоты на N дней вперёд для всех активных мастеров.

    Используется и сидером (на старте), и rolling-job-ом scheduler-а
    (каждый день добавляет +N+1 день).
    """
    from sqlalchemy import select

    if starting_from is None:
        starting_from = salon_today()
    masters_rows = await session.execute(select(Master).where(Master.is_active.is_(True)))
    masters = list(masters_rows.scalars().all())
    services_rows = await session.execute(select(Service).where(Service.is_active.is_(True)))
    services_by_id = {s.id: s for s in services_rows.scalars().all()}
    total = 0
    for d_offset in range(days):
        target = starting_from + timedelta(days=d_offset)
        for m in masters:
            total += await generate_slots_for_day(
                session,
                master=m,
                target_date=target,
                services_by_id=services_by_id,
            )
    await session.commit()
    return total


async def generate_one_day_ahead(session: AsyncSession, *, horizon_days: int = 14) -> int:
    """Rolling-window job: добавить слоты на единственный день `today + horizon_days`."""
    target = salon_today() + timedelta(days=horizon_days)
    return await generate_slots_window(session, days=1, starting_from=target)
