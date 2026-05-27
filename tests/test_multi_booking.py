"""Составные запросы: две услуги на разные дни."""
from __future__ import annotations

from services.multi_booking import extract_booking_segments, looks_like_booking_request


def test_extract_massage_tomorrow_manicure_day_after() -> None:
    services = ["Маникюр", "Массаж", "Стрижка (без окрашивания)"]
    text = "хорошо, давайте завтра массаж, а послезавтра на маникюр"
    segs = extract_booking_segments(text, services)
    assert len(segs) == 2
    assert segs[0].service_name == "Массаж"
    assert segs[1].service_name == "Маникюр"
    assert segs[0].date_hint
    assert segs[1].date_hint
    assert segs[0].date_hint != segs[1].date_hint


def test_looks_like_booking_davayte() -> None:
    services = ["Маникюр", "Массаж"]
    assert looks_like_booking_request("давайте завтра массаж", services)
