"""Repository для услуг."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Service


class ServiceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_active(self) -> list[Service]:
        rows = await self._s.execute(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.name),
        )
        return list(rows.scalars().all())

    async def get(self, service_id: int) -> Service | None:
        return await self._s.get(Service, service_id)

    async def create(self, *, name: str, duration_min: int, price_kop: int) -> Service:
        svc = Service(name=name, duration_min=duration_min, price_kop=price_kop)
        self._s.add(svc)
        await self._s.flush()
        return svc

    async def get_or_create(
        self, *, name: str, duration_min: int, price_kop: int,
    ) -> Service:
        existing = await self._s.execute(select(Service).where(Service.name == name))
        found = existing.scalar_one_or_none()
        if found:
            return found
        return await self.create(name=name, duration_min=duration_min, price_kop=price_kop)
