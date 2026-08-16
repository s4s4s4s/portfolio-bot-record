"""Тесты UX-плана: телефон, persona, gibberish, карточки."""

from __future__ import annotations

import re

import pytest

from services.booking_format import fmt_confirm_body
from services.complaint_detect import looks_like_gibberish
from services.persona import (
    booking_created,
    did_not_understand_message,
    phone_after_name,
    phone_invalid_error,
    unsupported_service_message,
)
from services.phone import normalize_phone
from services.slot_matching import filter_slots_exact, parse_time_hint


def test_normalize_phone_ten_digits() -> None:

    assert normalize_phone("9153108217") == "+79153108217"





@pytest.mark.asyncio

async def test_phone_invalid_scene() -> None:

    msg = await phone_invalid_error()

    assert "phone_invalid" in msg





@pytest.mark.asyncio

async def test_phone_after_name_scene() -> None:

    t = await phone_after_name()

    assert "enter_phone" in t

    named = await phone_after_name(first_name="Фатима")

    assert "enter_phone" in named

    assert "Фатима" in named





@pytest.mark.asyncio

async def test_unsupported_service_scene() -> None:

    msg = await unsupported_service_message("мелирование", ["Маникюр", "Массаж"], quoted=False)

    assert "unsupported_service" in msg





@pytest.mark.asyncio

async def test_unsupported_with_user_text() -> None:

    msg = await unsupported_service_message(

        "мелирование", ["Маникюр"], user_text="добрый день, как дела",

    )

    assert "unsupported_service" in msg





def test_gibberish_detected() -> None:

    assert looks_like_gibberish("орпролполпол")





@pytest.mark.asyncio

async def test_did_not_understand_scene() -> None:

    msg = await did_not_understand_message()

    assert "did_not_understand" in msg





def test_confirm_body_multiline() -> None:

    body = fmt_confirm_body(

        "Массаж", "Дмитрий", "29.05 Пт 19:00", 60, 2500, "Арсений", "+79153108217",

    )

    assert "Мастер: Дмитрий" in body

    assert not re.search(r"Массаж · Дмитрий · 29", body)





@pytest.mark.asyncio

async def test_booking_created_scene() -> None:

    msg = await booking_created("20.05 15:00", "Анна")

    assert "booking_created" in msg

    assert "20.05 15:00" in msg





def test_parse_time_hint() -> None:

    assert parse_time_hint("15:30") == (15, 30)





def test_filter_slots_exact() -> None:

    from datetime import datetime

    from db.models import Slot



    s1 = Slot(id=1, master_id=1, service_id=1, start_at=datetime(2026, 5, 21, 15, 0), status="available")

    s2 = Slot(id=2, master_id=1, service_id=1, start_at=datetime(2026, 5, 21, 15, 30), status="available")

    exact = filter_slots_exact([s1, s2], "15:30")

    assert len(exact) == 1

    assert exact[0].id == 2





@pytest.mark.asyncio

async def test_persona_scenes_use_llm_mock() -> None:

    from services.persona import (
        booking_cancelled,
        name_prompt,
        step_cancelled,
    )



    blob = "\n".join([

        await booking_created("1.1 12:00", "Дмитрий"),

        await booking_cancelled(),

        await did_not_understand_message(),

        await name_prompt(),

        await step_cancelled(),

    ])

    assert "1.1 12:00" in blob
    assert "booking_cancelled" in blob
    assert "шаг" not in blob.lower()


