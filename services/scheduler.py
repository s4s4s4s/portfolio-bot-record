"""APScheduler-обвязка.

Job-ы:
  • reminder_24h — каждые 15 мин, проверка bookings в окне now+23h..now+24h.
  • reminder_2h  — каждые 5 мин, проверка bookings в окне now+1h45m..now+2h.
  • rolling_slots — ежедневно в 03:00 локали, добавляет слотов на (today + 14 дней).
  • cleanup_old_slots — еженедельно (пн 04:00), удаляет старые available/blocked.

Используется MemoryJobStore: все jobs cron'овые, регистрируются идемпотентно
на старте через register_jobs(). Persistence в БД не требуется и создавала бы
конфликт с pickling сложных kwargs (например, notifier с SSL-контекстом).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import get_settings
from core.logging import get_logger
from db.repositories import BookingRepo
from db.session import get_session
from services.notifier import Notifier
from services.salon_time import is_past_slot, salon_now_naive
from services.service_grammar import service_speech_label
from services.slot_generator import generate_one_day_ahead

log = get_logger()


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    return AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        executors={"default": AsyncIOExecutor()},
        timezone=settings.tz,
    )


# ── Job functions ─────────────────────────────────────────────────────


async def job_reminder(*, kind: str, notifier_factory: object | None = None) -> int:
    """Универсальный reminder. kind: "24h" | "2h"."""
    settings = get_settings()
    if kind == "24h":
        offset_min = settings.reminder_offset_24h_min
        window_min = 60
    elif kind == "2h":
        offset_min = settings.reminder_offset_2h_min
        window_min = 15
    else:
        raise ValueError(f"unknown reminder kind: {kind!r}")
    now = salon_now_naive()
    after = now + timedelta(minutes=offset_min - window_min)
    before = now + timedelta(minutes=offset_min)

    sent = 0
    async with get_session() as session:
        booking_repo = BookingRepo(session)
        bookings = await booking_repo.list_due_for_reminder(
            after=after, before=before, kind=kind,
        )
        for b in bookings:
            slot = b.slot
            client = b.client
            service = slot.service if slot else None
            master = slot.master if slot else None
            if not (slot and client and service and master):
                continue
            if is_past_slot(slot.start_at, now=now):
                continue
            text = (
                f"⏰ Напоминание: запись на {slot.start_at.strftime('%d.%m %H:%M')}\n"
                f"Услуга: {service_speech_label(service.name)}\n"
                f"Мастер: {master.name}"
            )
            notifier = _notifier_or_default(notifier_factory)
            ok = await notifier.send(tg_user_id=client.tg_user_id, text=text)
            if ok:
                await booking_repo.mark_reminded(b, kind=kind)
                sent += 1
        await session.commit()
    log.info(f"reminder_{kind}: отправлено {sent} напоминаний")
    return sent


def _notifier_or_default(factory: object | None) -> Notifier:
    """factory — либо callable, возвращающий Notifier, либо готовый Notifier, либо None."""
    if factory is None:
        from services.notifier import InMemoryNotifier
        return InMemoryNotifier()
    if callable(factory):
        return factory()  # type: ignore[no-any-return]
    return factory  # type: ignore[return-value]


async def job_rolling_slots() -> int:
    """Догенерить слотов на (today + 14d)."""
    async with get_session() as session:
        created = await generate_one_day_ahead(session, horizon_days=14)
    log.info(f"rolling_slots: создано {created} слотов")
    return created


async def job_cleanup_old_slots(retention_days: int = 30) -> int:
    """Удаляет slots где start_at < now - retention_days и status != 'booked'."""
    from sqlalchemy import delete

    from db.models import Slot

    cutoff = salon_now_naive() - timedelta(days=retention_days)
    async with get_session() as session:
        result = await session.execute(
            delete(Slot).where(Slot.start_at < cutoff, Slot.status != "booked"),
        )
        await session.commit()
    deleted = int(result.rowcount or 0)
    log.info(f"cleanup_old_slots: удалено {deleted} слотов")
    return deleted


# ── Регистрация ───────────────────────────────────────────────────────


def register_jobs(scheduler: AsyncIOScheduler, *, notifier_factory: object | None = None) -> None:
    settings = get_settings()
    scheduler.add_job(
        job_reminder,
        trigger=CronTrigger(minute="*/15"),
        kwargs={"kind": "24h", "notifier_factory": notifier_factory},
        id="reminder_24h", replace_existing=True,
    )
    scheduler.add_job(
        job_reminder,
        trigger=CronTrigger(minute="*/5"),
        kwargs={"kind": "2h", "notifier_factory": notifier_factory},
        id="reminder_2h", replace_existing=True,
    )
    scheduler.add_job(
        job_rolling_slots,
        trigger=CronTrigger(hour=settings.rolling_hour_local, minute=0),
        id="rolling_slots", replace_existing=True,
    )
    scheduler.add_job(
        job_cleanup_old_slots,
        trigger=CronTrigger(day_of_week="mon", hour=4, minute=0),
        id="cleanup_old_slots", replace_existing=True,
    )
