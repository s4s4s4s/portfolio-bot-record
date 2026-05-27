"""Тесты синонимов и недоступных услуг."""
from __future__ import annotations

from services.service_aliases import detect_unsupported_service, normalize_service_hint


def test_detect_unsupported_melirovanie() -> None:
    m = detect_unsupported_service("Хочу записаться на мелирование")
    assert m is not None
    assert m.label == "мелирование"
    assert m.quoted is False


def test_detect_unsupported_from_entity() -> None:
    m = detect_unsupported_service("", "мелирование")
    assert m is not None
    assert m.label == "мелирование"


def test_detect_quoted_unsupported() -> None:
    m = detect_unsupported_service("хочу золотой дождь")
    assert m is not None
    assert m.quoted is True


def test_detect_supported_none() -> None:
    assert detect_unsupported_service("запиши на маникюр") is None


def test_normalize_strizhka_alias() -> None:
    assert normalize_service_hint("стрижку") == "стрижка"
