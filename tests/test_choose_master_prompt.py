"""Фразы выбора мастера и даты — через LLM + ПРИМЕР."""
from __future__ import annotations

import pytest

from services.copy_variants import master_dative
from services.human_reply import _SCENE_EXAMPLES, _fill_example


def test_choose_master_example() -> None:
    text = _fill_example(_SCENE_EXAMPLES["choose_master"], {})
    assert "мастер" in text.lower()
    assert "принимает" not in text.lower()


def test_master_dative() -> None:
    assert master_dative("Дмитрий") == "Дмитрию"
    assert master_dative("Анна") == "Анне"


def test_choose_date_example() -> None:
    text = _fill_example(_SCENE_EXAMPLES["choose_date"], {"master": "Дмитрию"})
    assert "Дмитрию" in text


@pytest.mark.asyncio
async def test_persona_choose_master() -> None:
    from services import persona

    text = await persona.choose_master_prompt()
    assert "choose_master" in text or "мастер" in text.lower()
