"""Дата в запросе: фильтр мастеров и альтернативы."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from db.repositories import MasterRepo, ServiceRepo, SlotRepo
from services.booking_hints import extract_date_time
from services.date_master_offer import collect_masters_on_date
from services.human_reply import _SCENE_EXAMPLES, _fill_example
from services.salon_time import salon_today


def _next_saturday() -> date:
    today = salon_today()
    delta = (5 - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


@pytest.mark.asyncio
async def test_saturday_only_maria_has_slots(session_with_seed) -> None:  # type: ignore[no-untyped-def]
    s = session_with_seed
    haircut = next(x for x in await ServiceRepo(s).list_active() if "Стрижка" in x.name)
    saturday = _next_saturday()
    masters = await MasterRepo(s).list_for_service(haircut.id)
    anna = next(m for m in masters if m.name == "Анна")
    maria = next(m for m in masters if m.name == "Мария")

    anna_slots = await SlotRepo(s).list_available_on_date(anna.id, saturday, haircut.id)
    maria_slots = await SlotRepo(s).list_available_on_date(maria.id, saturday, haircut.id)
    assert not anna_slots
    assert maria_slots

    on_date = await collect_masters_on_date(s, service_id=haircut.id, target=saturday)
    assert len(on_date) == 1
    assert on_date[0].name == "Мария"


def test_extract_sb_sets_pending_saturday() -> None:
    date_hint, _ = extract_date_time("запиши на стрижку в сб")
    assert date_hint == _next_saturday().isoformat()


def test_date_miss_one_alt_example_genitive() -> None:
    facts = {
        "date_label": "субботу, 30.05",
        "master": "Анна",
        "master_genitive": "Анны",
        "alt": "Дмитрий",
        "alt_genitive": "Димы",
    }
    msg = _fill_example(_SCENE_EXAMPLES["date_miss_one_alt"], facts)
    assert "у Анны мест нет" in msg
    assert "у Димы есть" in msg
