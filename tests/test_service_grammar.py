"""Склонение названий услуг."""
from __future__ import annotations

from services.service_grammar import service_accusative, service_speech_label


def test_speech_label_strips_parenthetical() -> None:
    assert service_speech_label("Стрижка (без окрашивания)") == "Стрижка"


def test_accusative_strizhka() -> None:
    assert service_accusative("Стрижка (без окрашивания)") == "стрижку"


def test_accusative_manicure_invariable() -> None:
    assert service_accusative("Маникюр") == "маникюр"


def test_no_masters_message() -> None:
    from services.service_grammar import no_masters_message

    msg = no_masters_message("Стрижка (без окрашивания)")
    assert "стрижку" in msg
    assert "без окрашивания" not in msg
    assert "«" not in msg
