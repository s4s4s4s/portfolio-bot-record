"""Repository для admin_logs."""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AdminLog


class AdminLogRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def write(
        self,
        *,
        admin_tg_id: int,
        action: str,
        payload: dict[str, object] | None = None,
    ) -> AdminLog:
        entry = AdminLog(
            admin_tg_id=admin_tg_id,
            action=action,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
        self._s.add(entry)
        await self._s.flush()
        return entry
