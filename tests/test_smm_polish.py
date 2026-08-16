"""Пост-правка SMM-текста."""

from __future__ import annotations

from services.human_reply import _polish_smm


def test_ty_replaced() -> None:

    assert "тебе" not in _polish_smm("Когда тебе удобно прийти?").lower()





def test_broken_vam_hotela() -> None:
    out = _polish_smm("На какую дату вам бы хотела записаться")
    assert "хотела" not in out.lower() or "вам удобно" in out.lower()


def test_ghost_number_list_stripped() -> None:
    out = _polish_smm("Какую услугу 1. 2. 3. 4. 5.")
    assert "1." not in out
    assert "Какую услугу" in out


def test_polite_pronouns_lowercase() -> None:
    out = _polish_smm("Рада снова видеть Вас! Вам удобно записаться?")
    assert "Вас" not in out
    assert "Вам" not in out
    assert "вас" in out
    assert "вам" in out


