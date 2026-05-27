"""Repository для мастеров."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Master


class MasterRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_active(self) -> list[Master]:
        rows = await self._s.execute(
            select(Master).where(Master.is_active.is_(True)).order_by(Master.name),
        )
        return list(rows.scalars().all())

    async def get(self, master_id: int) -> Master | None:
        return await self._s.get(Master, master_id)

    async def list_for_service(self, service_id: int) -> list[Master]:
        """Все активные мастера, у которых service_id есть в services_csv."""
        all_active = await self.list_active()
        result: list[Master] = []
        for m in all_active:
            ids = {int(s.strip()) for s in m.services_csv.split(",") if s.strip().isdigit()}
            if service_id in ids:
                result.append(m)
        return result

    async def create(
        self, *, name: str, services_csv: str, schedule: dict[str, list[str]],
    ) -> Master:
        m = Master(
            name=name,
            services_csv=services_csv,
            schedule_json=json.dumps(schedule, ensure_ascii=False),
        )
        self._s.add(m)
        await self._s.flush()
        return m

    async def get_or_create(
        self, *, name: str, services_csv: str, schedule: dict[str, list[str]],
    ) -> Master:
        existing = await self._s.execute(select(Master).where(Master.name == name))
        found = existing.scalar_one_or_none()
        if found:
            return found
        return await self.create(name=name, services_csv=services_csv, schedule=schedule)

    @staticmethod
    def parse_schedule(master: Master) -> dict[str, list[str]]:
        try:
            data = json.loads(master.schedule_json)
            if isinstance(data, dict):
                return {str(k): list(v) for k, v in data.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return {}
