"""Отмена записей по тексту."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from services.booking_cancel import (
    ActiveBookingView,
    looks_like_cancel_all,
    looks_like_my_bookings,
    resolve_cancel_pick,
    resolve_cancel_target,
    should_cancel_existing_booking,
)

_V1 = ActiveBookingView(1, "Маникюр", "Дмитрий", "21.05 17:00")
_V2 = ActiveBookingView(2, "Маникюр", "Анна", "27.05 14:30")


def test_change_mind_multiple_cancels_latest() -> None:
    older = ActiveBookingView(1, "Маникюр", "Анна", "26.05 Вт 12:30")
    newer = ActiveBookingView(9, "Маникюр", "Анна", "04.06 Чт 11:30")
    r = resolve_cancel_target("я передумал", [older, newer])
    assert r.kind == "one"
    assert r.booking_id == 9


def test_change_mind_single() -> None:
    r = resolve_cancel_target("передумала", [_V1])
    assert r.kind == "one"
    assert r.booking_id == 1


def test_one_booking_plain_otmeni() -> None:
    r = resolve_cancel_target("отмени", [_V1])
    assert r.kind == "one"
    assert r.booking_id == 1


def test_two_bookings_plain_otmeni_asks() -> None:
    r = resolve_cancel_target("отмени", [_V1, _V2])
    assert r.kind == "ask"


def test_two_bookings_otmeni_zapis_asks() -> None:
    r = resolve_cancel_target("отмени запись", [_V1, _V2])
    assert r.kind == "ask"


def test_two_bookings_otmeni_time() -> None:
    v11 = ActiveBookingView(3, "Маникюр", "Анна", "28.05 Чт 11:00")
    v19 = ActiveBookingView(4, "Маникюр", "Дмитрий", "28.05 Чт 19:00")
    r = resolve_cancel_target("отмени запись на 11 00", [v11, v19])
    assert r.kind == "one"
    assert r.booking_id == 3


def test_two_bookings_otmeni_time_compact() -> None:
    v11 = ActiveBookingView(3, "Маникюр", "Анна", "28.05 Чт 11:00")
    v19 = ActiveBookingView(4, "Маникюр", "Дмитрий", "28.05 Чт 19:00")
    r = resolve_cancel_target("отмени запись на 1100", [v11, v19])
    assert r.kind == "one"
    assert r.booking_id == 3


def test_hinted_times_variants() -> None:
    from services.booking_cancel import _hinted_times_in_text

    assert "11:00" in _hinted_times_in_text("на 11 00")
    assert "11:00" in _hinted_times_in_text("на 11:00")
    assert "11:00" in _hinted_times_in_text("на 1100")


def test_two_bookings_otmeni_hour_only_asks() -> None:
    v11a = ActiveBookingView(3, "Массаж", "Дмитрий", "28.05 Чт 11:00", slot_on=date(2026, 5, 28))
    v11b = ActiveBookingView(4, "Маникюр", "Дмитрий", "30.05 Сб 11:00", slot_on=date(2026, 5, 30))
    r = resolve_cancel_target("отмени запись на 11", [v11a, v11b])
    assert r.kind == "ask"
    assert len(r.views) == 2


def test_looks_like_cancel_intent_no() -> None:
    from services.booking_cancel import looks_like_cancel_intent

    assert not looks_like_cancel_intent("нет")
    assert not looks_like_cancel_intent("Нет")
    assert looks_like_cancel_intent("отмени запись")
    assert looks_like_cancel_intent("нет", in_cancel_fsm=True)


def test_service_booking_escape() -> None:
    from services.booking_cancel import looks_like_service_booking_escape

    services = ["Маникюр", "Массаж", "Стрижка (без окрашивания)"]
    assert looks_like_service_booking_escape("Массаж", services)
    assert not looks_like_service_booking_escape("отмени массаж", services)


def test_otmeni_day_11_single() -> None:
    from datetime import date

    v = ActiveBookingView(5, "Массаж", "Анна", "11.06 Ср 15:00", slot_on=date(2026, 6, 11))
    r = resolve_cancel_target("отмени запись на 11", [v])
    assert r.kind == "one"
    assert r.booking_id == 5


def test_otmeni_day_11_multiple() -> None:
    from datetime import date

    views = [
        ActiveBookingView(1, "Массаж", "Анна", "11.05 Вс 10:00", slot_on=date(2026, 5, 11)),
        ActiveBookingView(2, "Маникюр", "Дмитрий", "11.06 Ср 15:00", slot_on=date(2026, 6, 11)),
    ]
    r = resolve_cancel_target("отмени на 11", views)
    assert r.kind == "ask"
    assert len(r.views) == 2


def test_otmeni_11_hour_and_day_union() -> None:
    from datetime import date

    hour_only = ActiveBookingView(1, "Массаж", "Дмитрий", "28.05 Чт 11:00", slot_on=date(2026, 5, 28))
    day_only = ActiveBookingView(2, "Маникюр", "Анна", "11.06 Ср 15:00", slot_on=date(2026, 6, 11))
    r = resolve_cancel_target("отмени на 11", [hour_only, day_only])
    assert r.kind == "ask"
    assert len(r.views) == 2


def test_two_bookings_otmeni_dmitry() -> None:
    r = resolve_cancel_target("отмени дмитрия", [_V1, _V2])
    assert r.kind == "one"
    assert r.booking_id == 1


def test_two_bookings_otmeni_anna() -> None:
    r = resolve_cancel_target("отмени анну", [_V1, _V2])
    assert r.kind == "one"
    assert r.booking_id == 2


def test_otmeni_unknown_master_not_found() -> None:
    r = resolve_cancel_target("отмени петра", [_V1, _V2])
    assert r.kind == "not_found"


def test_fsm_plain_otmeni_only_step() -> None:
    assert not should_cancel_existing_booking(
        "отмени", was_in_booking_fsm=True, views=[_V1, _V2],
    )


def test_fsm_otmeni_with_master_cancels_booking() -> None:
    assert should_cancel_existing_booking(
        "отмени дмитрия", was_in_booking_fsm=True, views=[_V1, _V2],
    )


def test_my_bookings_not_book_intent() -> None:
    assert looks_like_my_bookings("мои записи")
    from services.multi_booking import looks_like_booking_request

    assert not looks_like_booking_request("мои записи", ["Маникюр", "Массаж"])


def test_cancel_all_confirm_all() -> None:
    r = resolve_cancel_target("отмени все записи", [_V1, _V2])
    assert r.kind == "confirm_all"


def test_cancel_all_single_booking() -> None:
    r = resolve_cancel_target("отмени все записи", [_V1])
    assert r.kind == "one"
    assert r.booking_id == 1


def test_looks_like_cancel_all() -> None:
    assert looks_like_cancel_all("отмени все записи")
    assert not looks_like_cancel_all("отмени")


def test_not_in_fsm_always_tries_booking() -> None:
    assert should_cancel_existing_booking(
        "отмени", was_in_booking_fsm=False, views=[_V1],
    )


@patch("services.booking_cancel.salon_today", return_value=date(2026, 5, 26))
def test_pick_tomorrow_from_disambiguation(_mock_today: object) -> None:
    views = [
        ActiveBookingView(1, "Маникюр", "Анна", "26.05 11:00", slot_on=date(2026, 5, 26)),
        ActiveBookingView(2, "Маникюр", "Анна", "27.05 14:30", slot_on=date(2026, 5, 27)),
        ActiveBookingView(3, "Маникюр", "Анна", "27.05 18:00", slot_on=date(2026, 5, 27)),
    ]
    r = resolve_cancel_pick("которая на завтра", views)
    assert r.kind == "ask"
    assert len(r.views) == 2


@patch("services.booking_cancel.salon_today", return_value=date(2026, 5, 26))
def test_pick_tomorrow_unique(_mock_today: object) -> None:
    views = [
        ActiveBookingView(1, "Маникюр", "Анна", "26.05 11:00", slot_on=date(2026, 5, 26)),
        ActiveBookingView(2, "Маникюр", "Анна", "27.05 14:30", slot_on=date(2026, 5, 27)),
    ]
    r = resolve_cancel_pick("на завтра", views)
    assert r.kind == "one"
    assert r.booking_id == 2


def test_abort_cancel_pick_nikakuyu() -> None:
    from services.booking_cancel import looks_like_abort_cancel_pick

    assert looks_like_abort_cancel_pick("никакую")
    assert looks_like_abort_cancel_pick("не надо")
    assert looks_like_abort_cancel_pick("отмена")
    assert not looks_like_abort_cancel_pick("на завтра")
