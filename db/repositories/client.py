"""Repository для клиентов."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Client


class ClientRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_tg(self, tg_user_id: int) -> Client | None:
        rows = await self._s.execute(
            select(Client).where(Client.tg_user_id == tg_user_id),
        )
        return rows.scalar_one_or_none()

    async def upsert(
        self,
        *,
        tg_user_id: int,
        tg_username: str | None,
        full_name: str,
        phone: str,
    ) -> Client:
        existing = await self.get_by_tg(tg_user_id)
        if existing is not None:
            existing.tg_username = tg_username
            existing.full_name = full_name
            existing.phone = phone
            await self._s.flush()
            return existing
        c = Client(
            tg_user_id=tg_user_id,
            tg_username=tg_username,
            full_name=full_name,
            phone=phone,
        )
        self._s.add(c)
        await self._s.flush()
        return c

    async def list_all_ids(self) -> list[int]:
        rows = await self._s.execute(select(Client.tg_user_id))
        return [int(r[0]) for r in rows.all()]
