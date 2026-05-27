"""«Передумал» → отмена записи, не жалоба."""
from __future__ import annotations

from services.booking_cancel import (
    ActiveBookingView,
    should_cancel_existing_booking,
)
from services.complaint_detect import (
    looks_like_change_mind,
    looks_like_complaint,
)


def test_change_mind_not_complaint() -> None:
    assert looks_like_change_mind("я передумал!")
    assert not looks_like_complaint("я передумал!")


def test_change_mind_triggers_cancel() -> None:
    v = ActiveBookingView(1, "Массаж", "Дмитрий", "27.05 Ср 18:00")
    assert should_cancel_existing_booking(
        "я передумал", was_in_booking_fsm=False, views=[v],
    )
