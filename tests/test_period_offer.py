"""Тесты «завтра вечером» — быстрый выбор мастера."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from db.models import Slot
from services.human_reply import _SCENE_EXAMPLES, _fill_example
from services.period_offer import (
    build_period_offer_facts,
    extract_time_of_day,
    master_informal_at,
    slot_in_period,
)
from services.salon_time import salon_today


def test_extract_evening() -> None:
    assert extract_time_of_day("хочу на маникюр завтра вечером") == "evening"
    assert extract_time_of_day("утром") == "morning"


def test_master_informal() -> None:
    assert master_informal_at("Анна") == "Ани"
    assert master_informal_at("Дмитрий") == "Димы"


def test_period_offer_example() -> None:
    class M:
        def __init__(self, name: str) -> None:
            self.name = name

    tomorrow = salon_today() + timedelta(days=1)
    offers = [
        (M("Анна"), Slot(id=1, master_id=1, service_id=1, start_at=datetime(2026, 5, 28, 18, 30), status="available")),
        (M("Дмитрий"), Slot(id=2, master_id=2, service_id=1, start_at=datetime(2026, 5, 28, 20, 0), status="available")),
    ]
    facts = build_period_offer_facts(tomorrow, "evening", offers)
    text = _fill_example(_SCENE_EXAMPLES["period_master_offer"], facts)
    assert "завтрашний" in text
    assert "вечер" in text
    assert "Ани" in text
    assert "18:30" in text
    assert "Димы" in text
    assert "20:00" in text
    assert "К кому записать" in text


def test_slot_in_period_evening() -> None:
    slot = Slot(id=1, master_id=1, service_id=1, start_at=datetime(2026, 5, 28, 18, 30), status="available")
    assert slot_in_period(slot, "evening")
    assert not slot_in_period(
        Slot(id=2, master_id=1, service_id=1, start_at=datetime(2026, 5, 28, 11, 0), status="available"),
        "evening",
    )


@pytest.mark.asyncio
async def test_collect_period_offers(session_with_seed) -> None:
    from db.repositories import MasterRepo, ServiceRepo, SlotRepo
    from services.period_offer import collect_period_offers

    session = session_with_seed
    svc = (await ServiceRepo(session).list_active())[0]
    if svc.name != "Маникюр":
        for s in await ServiceRepo(session).list_active():
            if "маник" in s.name.lower():
                svc = s
                break
    target = salon_today() + timedelta(days=1)
    offers = await collect_period_offers(session, service_id=svc.id, target=target, period="evening")
    assert isinstance(offers, list)
