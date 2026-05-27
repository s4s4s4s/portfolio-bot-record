"""Тесты дневного лимита сообщений и блокировки."""
from __future__ import annotations

import pytest

from db.models import UserUsage
from db.repositories.user_usage import UserUsageRepo
from services.usage_limit import check_and_increment


def _usage(**kwargs: object) -> UserUsage:
    defaults = dict(
        tg_user_id=1,
        day_key="2026-05-20",
        msg_count=0,
        strike_count=0,
        last_violation_day=None,
        blocked=False,
        blocked_at=None,
    )
    defaults.update(kwargs)
    return UserUsage(**defaults)  # type: ignore[arg-type]


class TestCheckAndIncrement:
    def test_allows_under_limit(self):
        u = _usage()
        for _ in range(100):
            r = check_and_increment(u, today="2026-05-20", limit=100, strikes_before_block=3)
            assert r.allowed
        assert u.msg_count == 100

    def test_blocks_101st_with_strike(self):
        u = _usage(msg_count=100)
        r = check_and_increment(u, today="2026-05-20", limit=100, strikes_before_block=3)
        assert not r.allowed
        assert u.strike_count == 1
        assert u.last_violation_day == "2026-05-20"

    def test_no_double_strike_same_day(self):
        u = _usage(msg_count=100, strike_count=1, last_violation_day="2026-05-20")
        r = check_and_increment(u, today="2026-05-20", limit=100, strikes_before_block=3)
        assert not r.allowed
        assert u.strike_count == 1

    def test_block_after_third_strike_day(self):
        u = _usage(msg_count=100, strike_count=2, last_violation_day="2026-05-19")
        r = check_and_increment(u, today="2026-05-20", limit=100, strikes_before_block=3)
        assert not r.allowed
        assert u.blocked
        assert u.strike_count == 3

    def test_resets_count_new_day(self):
        u = _usage(msg_count=50, day_key="2026-05-19")
        r = check_and_increment(u, today="2026-05-20", limit=100, strikes_before_block=3)
        assert r.allowed
        assert u.msg_count == 1
        assert u.day_key == "2026-05-20"

    def test_blocked_user_stays_blocked(self):
        u = _usage(blocked=True, msg_count=0)
        r = check_and_increment(u, today="2026-05-20", limit=100, strikes_before_block=3)
        assert not r.allowed
        assert "ограничен" in (r.user_message or "").lower()


@pytest.mark.asyncio
async def test_repo_unblock(session) -> None:  # type: ignore[no-untyped-def]
    repo = UserUsageRepo(session)
    u = await repo.get_or_create(999)
    u.msg_count = 150
    u.strike_count = 3
    u.blocked = True
    await session.flush()

    out = await repo.unblock(999)
    assert out is not None
    assert not out.blocked
    assert out.strike_count == 0
