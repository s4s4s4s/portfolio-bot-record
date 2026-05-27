"""Короткий intro перед карточкой подтверждения — через LLM + ПРИМЕР."""
from __future__ import annotations

import pytest

from services.human_reply import _SCENE_EXAMPLES, _fill_example


def test_confirm_intro_example() -> None:
    text = _fill_example(_SCENE_EXAMPLES["confirm_intro"], {})
    assert text in ("Всё верно?", "Подтверждаем?") or "?" in text


def test_step_cancelled_example() -> None:
    text = _fill_example(_SCENE_EXAMPLES["step_cancelled"], {})
    assert "шаг" not in text.lower()


@pytest.mark.asyncio
async def test_persona_confirm_intro_uses_scene() -> None:
    from services import persona

    text = await persona.confirm_intro()
    assert "confirm_intro" in text or "?" in text
    assert "салон" not in text.lower()
    assert "перед записью" not in text.lower()


@pytest.mark.asyncio
async def test_persona_step_cancelled_uses_scene() -> None:
    from services import persona

    text = await persona.step_cancelled()
    assert "step_cancelled" in text or "запис" in text.lower()
    assert "шаг" not in text.lower()
