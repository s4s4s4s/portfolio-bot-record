"""Склонение имён мастеров."""

from __future__ import annotations



import pytest



from services.copy_variants import (

    date_step_nudge,

    master_genitive,

    master_is_feminine,

)





def test_master_genitive_anna() -> None:

    assert master_genitive("Анна") == "Анны"





def test_master_genitive_dmitry() -> None:

    assert master_genitive("Дмитрий") == "Дмитрия"





def test_master_feminine_anna() -> None:

    assert master_is_feminine("Анна") is True





@pytest.mark.asyncio

async def test_date_step_nudge_scene() -> None:

    msg = await date_step_nudge()

    assert "date_step_nudge" in msg


