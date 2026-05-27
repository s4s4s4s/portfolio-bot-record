"""Тесты переноса записи и парсинга времени."""
from __future__ import annotations

from services.booking_hints import extract_date_time
from services.reschedule_detect import looks_like_reschedule


def test_looks_like_reschedule() -> None:
    assert looks_like_reschedule("Перенеси мою запись")
    assert looks_like_reschedule("перенести запись")
    assert not looks_like_reschedule("запиши на стрижку")


def test_extract_time_spaced() -> None:
    _, time_hint = extract_date_time("15 00")
    assert time_hint == "15:00"
