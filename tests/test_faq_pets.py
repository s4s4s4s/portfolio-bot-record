"""FAQ про питомцев — до book intent."""

from __future__ import annotations

import pytest

from services.persona import faq_answer, looks_like_faq_request


def test_faq_pets_question() -> None:

    assert looks_like_faq_request("к вам с собачкой можно?")





@pytest.mark.asyncio

async def test_faq_pets_answer_scene() -> None:

    ans = await faq_answer("к вам с собачкой можно?")

    assert ans is not None

    assert "faq_pets" in ans





def test_kotoraya_not_pets_faq() -> None:

    assert not looks_like_faq_request("которая на завтра")





@pytest.mark.asyncio

async def test_kotoraya_no_faq_answer() -> None:

    assert await faq_answer("которая на завтра") is None


