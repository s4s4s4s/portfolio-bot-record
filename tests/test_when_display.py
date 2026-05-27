"""Формат даты/времени в карточках."""
from __future__ import annotations

from datetime import datetime

from services.booking_format import fmt_when_display, time_from_when_label


def test_fmt_when_display_weekday_no_year() -> None:
    # 2026-05-27 — среда
    dt = datetime(2026, 5, 27, 18, 0)
    s = fmt_when_display(dt)
    assert "2026" not in s
    assert "27.05" in s
    assert "Ср" in s
    assert "18:00" in s


def test_time_from_when_label_with_weekday() -> None:
    assert time_from_when_label("27.05 Ср 18:00") == "18:00"


def test_time_from_when_label_legacy() -> None:
    assert time_from_when_label("21.05 17:00") == "17:00"
