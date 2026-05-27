"""Грамматика фраз записи/отмены — LLM + пост-правка, без заготовленных текстов."""
from __future__ import annotations

import pytest

from services.human_reply import _polish_smm, booking_phrase_broken
from services.persona import booking_cancelled_detail, booking_created


def test_detect_broken_passive() -> None:
    assert booking_phrase_broken("вас отменили к Дмитрию на маникюр")
    assert booking_phrase_broken("вас записала к Дмитрию на 29.05")
    assert not booking_phrase_broken("Записала вас к Дмитрию на 29.05")
    assert not booking_phrase_broken("Отменила запись к Дмитрию на маникюр")


def test_polish_fixes_client_passive() -> None:
    fixed = _polish_smm("вас записала к Дмитрию на 29.05 Пт 11:00")
    assert "записала вас" in fixed.lower()
    assert "вас записала" not in fixed.lower()

    fixed2 = _polish_smm("вас отменили к Дмитрию")
    assert "вас отменил" not in fixed2.lower()


@pytest.mark.asyncio
async def test_booking_created_uses_llm_scene() -> None:
    msg = await booking_created("29.05 Пт 11:00", "Дмитрий")
    assert "booking_created" in msg
    assert "29.05 Пт 11:00" in msg


@pytest.mark.asyncio
async def test_booking_cancelled_detail_uses_llm_scene() -> None:
    msg = await booking_cancelled_detail("Маникюр", "Дмитрий", "29.05 Пт 11:00")
    assert "booking_cancelled_detail" in msg
    assert "29.05 Пт 11:00" in msg


@pytest.mark.asyncio
async def test_booking_cancelled_detail_fallback_on_broken_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _bad_say(scene: str, facts: dict | None = None, **kwargs: object) -> str:
        return "вас отменили к Дмитрию на маникюр"

    monkeypatch.setattr("services.human_reply.say", _bad_say)
    msg = await booking_cancelled_detail("Маникюр", "Дмитрий", "29.05 Пт 11:00")
    assert "отменила" in msg.lower()
    assert "вас отменили" not in msg.lower()
    assert "29.05 Пт 11:00" in msg
