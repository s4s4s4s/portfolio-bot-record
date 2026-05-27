"""Repository для user_usage (лимиты и блокировки)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserUsage
from services.usage_limit import UsageCheckResult, check_and_increment, today_key


class UserUsageRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, tg_user_id: int) -> UserUsage | None:
        return await self._s.get(UserUsage, tg_user_id)

    async def get_or_create(self, tg_user_id: int) -> UserUsage:
        row = await self.get(tg_user_id)
        if row is not None:
            return row
        today = today_key()
        row = UserUsage(
            tg_user_id=tg_user_id,
            day_key=today,
            msg_count=0,
            strike_count=0,
            last_violation_day=None,
            blocked=False,
            blocked_at=None,
        )
        self._s.add(row)
        await self._s.flush()
        return row

    async def record_incoming(self, tg_user_id: int, *, limit: int, strikes_before_block: int) -> UsageCheckResult:
        usage = await self.get_or_create(tg_user_id)
        return check_and_increment(
            usage,
            today=today_key(),
            limit=limit,
            strikes_before_block=strikes_before_block,
        )

    async def unblock(self, tg_user_id: int, *, reset_strikes: bool = True) -> UserUsage | None:
        usage = await self.get(tg_user_id)
        if usage is None:
            return None
        usage.blocked = False
        usage.blocked_at = None
        if reset_strikes:
            usage.strike_count = 0
            usage.last_violation_day = None
        await self._s.flush()
        return usage

    async def list_blocked(self) -> list[UserUsage]:
        rows = await self._s.execute(select(UserUsage).where(UserUsage.blocked.is_(True)))
        return list(rows.scalars().all())
