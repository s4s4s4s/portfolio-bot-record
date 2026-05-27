"""Off-topic и провокации — не отмена записи."""
from __future__ import annotations

from services.complaint_detect import looks_like_off_topic


def test_sosal_is_off_topic_not_cancel() -> None:
    assert looks_like_off_topic("Сосал?")
    assert looks_like_off_topic("сосал")


def test_booking_still_on_topic() -> None:
    assert not looks_like_off_topic("хочу на маникюр завтра")
    assert not looks_like_off_topic("сколько стоит стрижка?")


def test_cancel_not_off_topic() -> None:
    assert not looks_like_off_topic("отмена")
