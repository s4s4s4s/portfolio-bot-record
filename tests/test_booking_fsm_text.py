"""Тексты во время активной записи."""

from __future__ import annotations

import pytest

from services.booking_fsm_text import (
    looks_like_later_time_request,
    looks_like_waitlist_request,
    parse_min_time_hint,
    safe_client_first_name,
)
from services.persona import service_choice_prompt


def test_safe_name_blocks_vulgar() -> None:

    assert safe_client_first_name("сперма") is None

    assert safe_client_first_name("Арсений Иванов") == "Арсений"





def test_later_time_detect() -> None:

    assert looks_like_later_time_request("а позже 17 30 нельзя?")

    assert parse_min_time_hint("позже 17 30") == "17:30"





def test_waitlist_detect() -> None:

    assert looks_like_waitlist_request("сообщите если освободится позже 1730")





@pytest.mark.asyncio

async def test_service_choice_scene() -> None:

    msg = await service_choice_prompt(["Маникюр", "Массаж", "Стрижка (без окрашивания)"])

    assert "service_choice" in msg


