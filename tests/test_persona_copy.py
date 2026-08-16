"""Тесты persona + human_reply (мок LLM)."""

from __future__ import annotations

import pytest

from services.persona import (
    booking_created,
    name_prompt,
    welcome_with_catalog,
)
from services.phone import PHONE_HINT
from services.text_guard import sanitize_bot_text


@pytest.mark.asyncio

async def test_welcome_no_beauty_latin() -> None:
    text = await welcome_with_catalog(["Маникюр", "Стрижка (без окрашивания)"])
    assert "beauty" not in text.lower()
    assert "1." not in text
    assert "маникюр" in text.lower()
    assert "стрижку" in text.lower()
    assert "у нас" not in text.lower()





@pytest.mark.asyncio

async def test_sanitize_replaces_beauty() -> None:

    out = sanitize_bot_text("Добро пожаловать в beauty-салон!")

    assert "beauty" not in out.lower()

    assert "салон красоты" in out





@pytest.mark.asyncio

async def test_name_prompt_scene() -> None:

    msg = await name_prompt()

    assert "enter_name" in msg





def test_phone_hint_flexible() -> None:

    assert "формате" not in PHONE_HINT.lower()

    assert "+7 905" not in PHONE_HINT





@pytest.mark.asyncio

async def test_booking_created_scene() -> None:
    msg = await booking_created("29.05.2026 17:30", "Дмитрий")
    assert "booking_created" in msg
    assert "29.05.2026 17:30" in msg


