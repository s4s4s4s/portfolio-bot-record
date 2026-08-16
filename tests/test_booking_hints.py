"""Тесты извлечения даты/времени из живой речи."""
from __future__ import annotations

from services.booking_hints import extract_date_time


def test_na_8_is_time_not_date() -> None:
    _, time_hint = extract_date_time("к ане на 8")
    assert time_hint == "08:00"


def test_na_8_chasov() -> None:
    _, time_hint = extract_date_time("на 8 часов")
    assert time_hint == "08:00"


def test_na_8_vechera() -> None:
    _, time_hint = extract_date_time("на 8 вечера")
    assert time_hint == "20:00"


def test_v_sredu_is_date() -> None:
    date_hint, time_hint = extract_date_time("в среду")
    assert date_hint
    assert not time_hint


def test_v_sb_abbreviation() -> None:
    date_hint, _ = extract_date_time("стрижка в сб")
    assert date_hint
    from datetime import date

    from services.salon_time import salon_today

    parsed = date.fromisoformat(date_hint)
    assert parsed.weekday() == 5
    assert parsed >= salon_today()


def test_na_sb_abbreviation() -> None:
    date_hint, _ = extract_date_time("на сб")
    assert date_hint
    from datetime import date

    assert date.fromisoformat(date_hint).weekday() == 5


def test_na_8_e_is_date_not_time() -> None:
    date_hint, time_hint = extract_date_time("на 8-е")
    assert date_hint
    assert not time_hint
