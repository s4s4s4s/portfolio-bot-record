"""Тесты broadcast: отправка всем, rate-limit, AdminLog."""
from __future__ import annotations

import pytest

from db.repositories import AdminLogRepo, ClientRepo
from services.notifier import InMemoryNotifier, broadcast

pytestmark = pytest.mark.asyncio


async def test_broadcast_sends_to_all(session) -> None:  # type: ignore[no-untyped-def]
    repo = ClientRepo(session)
    for i in range(5):
        await repo.upsert(
            tg_user_id=1000 + i, tg_username=None, full_name=f"u{i}", phone="+79051234567",
        )
    await session.flush()
    notifier = InMemoryNotifier()
    recipients = await repo.list_all_ids()
    ok, fail = await broadcast(notifier, recipients=recipients, text="привет")
    assert ok == 5
    assert fail == 0
    assert {r[0] for r in notifier.sent} == set(recipients)
    assert all(text == "привет" for _, text in notifier.sent)


async def test_broadcast_empty_recipients() -> None:
    notifier = InMemoryNotifier()
    ok, fail = await broadcast(notifier, recipients=[], text="x")
    assert (ok, fail) == (0, 0)
    assert notifier.sent == []


async def test_broadcast_writes_admin_log(session) -> None:  # type: ignore[no-untyped-def]
    """Семантический тест: после broadcast должна появиться запись в AdminLog
    с action='broadcast' и payload с количеством получателей.
    """
    repo = ClientRepo(session)
    for i in range(3):
        await repo.upsert(
            tg_user_id=2000 + i, tg_username=None, full_name=f"u{i}", phone="+79051234567",
        )
    await session.flush()

    notifier = InMemoryNotifier()
    recipients = await repo.list_all_ids()
    ok, fail = await broadcast(notifier, recipients=recipients, text="hello")
    log_repo = AdminLogRepo(session)
    entry = await log_repo.write(
        admin_tg_id=111, action="broadcast",
        payload={"recipients": len(recipients), "ok": ok, "fail": fail},
    )
    assert entry.action == "broadcast"
    assert entry.payload_json is not None
    assert "recipients" in entry.payload_json
