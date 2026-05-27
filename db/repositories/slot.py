"""Repository для слотов."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Slot
from services.salon_time import salon_now_naive, slot_query_from


class SlotRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, slot_id: int) -> Slot | None:
        return await self._s.get(Slot, slot_id)

    async def find_by_master_start(self, master_id: int, start_at: datetime) -> Slot | None:
        rows = await self._s.execute(
            select(Slot).where(
                and_(Slot.master_id == master_id, Slot.start_at == start_at),
            ),
        )
        return rows.scalar_one_or_none()

    async def find_by_master_service_start(
        self, master_id: int, service_id: int, start_at: datetime,
    ) -> Slot | None:
        rows = await self._s.execute(
            select(Slot).where(
                and_(
                    Slot.master_id == master_id,
                    Slot.service_id == service_id,
                    Slot.start_at == start_at,
                ),
            ),
        )
        return rows.scalar_one_or_none()

    async def has_time_overlap(
        self, master_id: int, start_at: datetime, end_at: datetime,
    ) -> bool:
        """Есть ли у мастера слот, интервал которого пересекается с [start_at, end_at).

        Полуинтервалы [start, end): пересечение если existing.start < end AND existing.end > start.
        """
        rows = await self._s.execute(
            select(Slot.id).where(
                and_(
                    Slot.master_id == master_id,
                    Slot.start_at < end_at,
                    Slot.end_at > start_at,
                ),
            ).limit(1),
        )
        return rows.scalar_one_or_none() is not None

    async def list_available_dates(self, master_id: int, *, service_id: int | None = None, days: int = 14) -> list[date]:
        """Уникальные даты (UTC date) у мастера со статусом available, отсортированы.

        Если передан service_id — возвращает только даты, на которые есть свободные слоты
        именно для этой услуги.
        """
        now = salon_now_naive()
        upper = now + timedelta(days=days)
        conds = [
            Slot.master_id == master_id,
            Slot.status == "available",
            Slot.start_at >= now,
            Slot.start_at < upper,
        ]
        if service_id is not None:
            conds.append(Slot.service_id == service_id)
        rows = await self._s.execute(
            select(Slot.start_at)
            .where(and_(*conds))
            .order_by(Slot.start_at),
        )
        unique_dates: list[date] = []
        seen: set[date] = set()
        for (dt,) in rows.all():
            d = dt.date()
            if d not in seen:
                seen.add(d)
                unique_dates.append(d)
        return unique_dates

    async def list_available_on_date(
        self, master_id: int, target_date: date, service_id: int | None = None,
    ) -> list[Slot]:
        earliest = slot_query_from(target_date)
        if earliest is None:
            return []
        end = datetime.combine(target_date, time.min) + timedelta(days=1)
        conds = [
            Slot.master_id == master_id,
            Slot.status == "available",
            Slot.start_at >= earliest,
            Slot.start_at < end,
        ]
        if service_id is not None:
            conds.append(Slot.service_id == service_id)
        rows = await self._s.execute(
            select(Slot).where(and_(*conds)).order_by(Slot.start_at),
        )
        return list(rows.scalars().all())

    async def list_active_in_range(
        self, *, after: datetime, before: datetime,
    ) -> list[Slot]:
        rows = await self._s.execute(
            select(Slot).where(
                Slot.start_at >= after,
                Slot.start_at < before,
                Slot.status == "booked",
            ).order_by(Slot.start_at),
        )
        return list(rows.scalars().all())

    async def create_available(
        self,
        *,
        master_id: int,
        service_id: int,
        start_at: datetime,
        duration_min: int,
    ) -> Slot:
        slot = Slot(
            master_id=master_id,
            service_id=service_id,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=duration_min),
            status="available",
        )
        self._s.add(slot)
        await self._s.flush()
        return slot

    async def block(self, slot: Slot) -> None:
        if slot.status == "booked":
            raise ValueError("cannot block already-booked slot")
        slot.status = "blocked"
        await self._s.flush()

    async def reserve_atomic(self, slot_id: int) -> Slot | None:
        """Атомарно перевести слот в booked. Возвращает Slot если удалось,
        None — если слот уже занят/заблокирован/удалён.

        SQLAlchemy не имеет SELECT FOR UPDATE для SQLite; используем
        UPDATE ... WHERE status='available' и проверяем rowcount.
        """
        from sqlalchemy import update

        result = await self._s.execute(
            update(Slot)
            .where(
                Slot.id == slot_id,
                Slot.status == "available",
                Slot.start_at >= salon_now_naive(),
            )
            .values(status="booked"),
        )
        if result.rowcount != 1:
            return None
        return await self._s.get(Slot, slot_id)
