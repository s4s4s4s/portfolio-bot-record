"""Repository для бронирований."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Booking, Slot


class BookingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, booking_id: int) -> Booking | None:
        return await self._s.get(Booking, booking_id)

    async def get_by_slot_id(self, slot_id: int) -> Booking | None:
        rows = await self._s.execute(
            select(Booking).where(Booking.slot_id == slot_id),
        )
        return rows.scalar_one_or_none()

    async def create(self, *, slot_id: int, client_id: int) -> Booking:
        booking = Booking(slot_id=slot_id, client_id=client_id, status="active")
        self._s.add(booking)
        await self._s.flush()
        return booking

    async def create_active_for_slot(self, *, slot_id: int, client_id: int) -> Booking:
        """Создать бронь или реактивировать отменённую на том же slot_id."""
        existing = await self.get_by_slot_id(slot_id)
        if existing is not None:
            if existing.status == "active":
                return existing
            if existing.status == "cancelled":
                existing.status = "active"
                existing.client_id = client_id
                existing.cancel_reason = None
                existing.reminded_24h = False
                existing.reminded_2h = False
                await self._s.flush()
                return existing
        return await self.create(slot_id=slot_id, client_id=client_id)

    async def list_active_for_client(self, client_id: int) -> list[Booking]:
        rows = await self._s.execute(
            select(Booking)
            .options(selectinload(Booking.slot).selectinload(Slot.master),
                     selectinload(Booking.slot).selectinload(Slot.service))
            .join(Slot, Booking.slot_id == Slot.id)
            .where(Booking.client_id == client_id, Booking.status == "active")
            .order_by(Slot.start_at.asc()),
        )
        return list(rows.scalars().all())

    async def list_active_in_range(
        self, *, after: datetime, before: datetime,
    ) -> list[Booking]:
        rows = await self._s.execute(
            select(Booking)
            .options(selectinload(Booking.slot).selectinload(Slot.master),
                     selectinload(Booking.slot).selectinload(Slot.service),
                     selectinload(Booking.client))
            .join(Slot, Booking.slot_id == Slot.id)
            .where(
                and_(
                    Booking.status == "active",
                    Slot.start_at >= after,
                    Slot.start_at < before,
                ),
            )
            .order_by(Slot.start_at),
        )
        return list(rows.scalars().all())

    async def cancel(self, booking: Booking, *, reason: str | None = None) -> None:
        # Async-lazy-load запрещён без greenlet — НЕ трогаем booking.slot напрямую,
        # подгружаем slot через session.get по slot_id.
        from db.models import Slot
        slot = await self._s.get(Slot, booking.slot_id)
        booking.status = "cancelled"
        booking.cancel_reason = reason
        if slot is not None:
            slot.status = "available"
            slot.booking_id = None
        await self._s.flush()

    async def list_due_for_reminder(
        self,
        *,
        after: datetime,
        before: datetime,
        kind: str,
    ) -> list[Booking]:
        if kind == "24h":
            cond = Booking.reminded_24h.is_(False)
        elif kind == "2h":
            cond = Booking.reminded_2h.is_(False)
        else:
            raise ValueError(f"unknown reminder kind: {kind!r}")
        rows = await self._s.execute(
            select(Booking)
            .options(selectinload(Booking.slot).selectinload(Slot.master),
                     selectinload(Booking.slot).selectinload(Slot.service),
                     selectinload(Booking.client))
            .join(Slot, Booking.slot_id == Slot.id)
            .where(
                Booking.status == "active",
                cond,
                Slot.start_at >= after,
                Slot.start_at < before,
            ),
        )
        return list(rows.scalars().all())

    async def mark_reminded(self, booking: Booking, *, kind: str) -> None:
        if kind == "24h":
            booking.reminded_24h = True
        elif kind == "2h":
            booking.reminded_2h = True
        else:
            raise ValueError(f"unknown reminder kind: {kind!r}")
        await self._s.flush()
