"""Отмена готовых записей по тексту («отмени», «отмени Дмитрия»)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from db.models import Booking
from services.booking_format import fmt_when_display, time_from_when_label
from services.master_matching import master_matches_text
from services.salon_time import salon_today

_CANCEL_WORDS = ("отмен", "стоп", "не надо")
_ABORT_CANCEL_PICK = (
    "никак", "ни одну", "ни одна", "ни одной", "ни одного", "ничего",
    "не отмен", "оставь", "назад", "выход", "хватит", "передумал", "передумала",
)
_BOOKING_HINT_WORDS = ("запис", "бронь", "визит", "приём", "прием", "окно")
_CANCEL_STRIP_RE = re.compile(
    r"\b(отмени|отмена|отменить|отмену|стоп|не\s+надо)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActiveBookingView:
    booking_id: int
    service_name: str
    master_name: str
    when_label: str
    slot_on: date | None = None


@dataclass(frozen=True)
class CancelResolve:
    kind: Literal["none", "one", "ask", "not_found", "confirm_all"]
    booking_id: int | None = None
    views: tuple[ActiveBookingView, ...] = ()


def booking_views_from_models(bookings: list[Booking]) -> list[ActiveBookingView]:
    views: list[ActiveBookingView] = []
    for b in bookings:
        slot = b.slot
        if slot is None:
            continue
        service = slot.service
        master = slot.master
        if service is None or master is None:
            continue
        when = fmt_when_display(slot.start_at)
        views.append(
            ActiveBookingView(
                booking_id=b.id,
                service_name=service.name,
                master_name=master.name,
                when_label=when,
                slot_on=slot.start_at.date(),
            ),
        )
    return views


def looks_like_my_bookings(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in ("мои запис", "моя запись", "мои визит", "мои брони"))


def looks_like_cancel_all(text: str) -> bool:
    low = text.lower()
    if not _has_cancel_word(text):
        return False
    return any(
        p in low
        for p in (
            "отмени все", "отменить все", "отмена всех", "все записи",
            "все визиты", "все брони", "отмени всё", "отменить всё",
        )
    )


def looks_like_cancel_all_confirm(text: str) -> bool:
    low = text.lower().strip()
    return low in ("да", "да.", "ага", "угу", "подтверждаю", "точно", "yes", "ok", "ок") or any(
        p in low for p in ("да, отмен", "да отмен", "отменяй", "отменяйте")
    )


def _has_cancel_word(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _CANCEL_WORDS)


def looks_like_abort_cancel_pick(text: str) -> bool:
    """Выход из выбора «какую запись отменить» без отмены."""
    low = text.lower().strip()
    if not low:
        return False
    if _has_cancel_word(text):
        return True
    return any(m in low for m in _ABORT_CANCEL_PICK)


def _service_matches_text(service_name: str, text: str) -> bool:
    low = text.lower()
    name = service_name.lower()
    stem = name.split("(")[0].strip()
    if len(stem) >= 4 and stem[:5] in low:
        return True
    return stem in low if len(stem) >= 3 else False


def _relative_day_matches(text: str, slot_on: date) -> bool:
    low = text.lower()
    today = salon_today()
    if "послезавтра" in low:
        return slot_on == today + timedelta(days=2)
    if "завтра" in low:
        return slot_on == today + timedelta(days=1)
    if "сегодня" in low:
        return slot_on == today
    return False


def _hinted_times_in_text(text: str) -> set[str]:
    """11:00, 11 00, 11.00, 1100 → {'11:00'}."""
    out: set[str] = set()
    for m in re.finditer(r"(?<!\d)(\d{1,2})\s*[.:]?\s*(\d{2})(?!\d)", text):
        out.add(f"{int(m.group(1)):02d}:{m.group(2)}")
    for m in re.finditer(r"(?<!\d)(\d{2})(\d{2})(?!\d)", text):
        out.add(f"{int(m.group(1)):02d}:{m.group(2)}")
    return out


def _hinted_hours_in_text(text: str) -> set[int]:
    """«на 11», «в 19» без минут."""
    out: set[int] = set()
    for m in re.finditer(
        r"(?:^|[\s,])(?:на|в)\s*(\d{1,2})(?!\s*[.:]\d)",
        text,
        re.IGNORECASE,
    ):
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            out.add(hour)
    return out


def _hour_from_time_label(time_part: str) -> int | None:
    m = re.match(r"(\d{1,2}):\d{2}", time_part)
    return int(m.group(1)) if m else None


def _when_matches_text(when_label: str, text: str, *, slot_on: date | None = None) -> bool:
    if slot_on is not None and _relative_day_matches(text, slot_on):
        return True
    low = text.lower().replace(" ", "")
    date_part = when_label.split()[0]
    if date_part.replace(".", "") in low.replace(".", ""):
        return True
    if date_part in text:
        return True
    time_part = time_from_when_label(when_label)
    if time_part:
        if time_part in text or time_part in _hinted_times_in_text(text):
            return True
        hinted_hours = _hinted_hours_in_text(text)
        slot_hour = _hour_from_time_label(time_part)
        if slot_hour is not None and slot_hour in hinted_hours:
            return True
    m = re.search(r"(\d{1,2})[.:](\d{2})", text)
    if m and f"{int(m.group(1)):02d}.{m.group(2)}" == date_part:
        return True
    return False


def _view_hour(view: ActiveBookingView) -> int | None:
    return _hour_from_time_label(time_from_when_label(view.when_label))


def _views_for_hour(views: list[ActiveBookingView], hour: int) -> list[ActiveBookingView]:
    if hour > 23:
        return []
    return [v for v in views if _view_hour(v) == hour]


def _views_for_day_of_month(views: list[ActiveBookingView], day: int) -> list[ActiveBookingView]:
    if not 1 <= day <= 31:
        return []
    return [v for v in views if v.slot_on is not None and v.slot_on.day == day]


def _views_matching_full_time(text: str, views: list[ActiveBookingView]) -> list[ActiveBookingView]:
    times = _hinted_times_in_text(text)
    if not times:
        return []
    return [v for v in views if time_from_when_label(v.when_label) in times]


def _merge_unique_views(*groups: list[ActiveBookingView]) -> list[ActiveBookingView]:
    seen: set[int] = set()
    out: list[ActiveBookingView] = []
    for group in groups:
        for v in group:
            if v.booking_id in seen:
                continue
            seen.add(v.booking_id)
            out.append(v)
    return out


def _resolve_hour_and_day_hints(
    text: str, views: list[ActiveBookingView],
) -> list[ActiveBookingView] | None:
    """Число после «на» — и час, и число месяца. None = hint не применялся."""
    by_time = _views_matching_full_time(text, views)
    if by_time:
        return by_time

    numbers = _hinted_hours_in_text(text)
    if not numbers:
        return None

    hour_views: list[ActiveBookingView] = []
    day_views: list[ActiveBookingView] = []
    for n in numbers:
        hour_views = _merge_unique_views(hour_views, _views_for_hour(views, n))
        day_views = _merge_unique_views(day_views, _views_for_day_of_month(views, n))

    has_hour = bool(hour_views)
    has_day = bool(day_views)
    if not has_hour and not has_day:
        return []

    if has_hour and not has_day:
        return hour_views
    if has_day and not has_hour:
        return day_views
    return _merge_unique_views(hour_views, day_views)


def _finalize_candidates(
    candidates: list[ActiveBookingView],
    all_views: list[ActiveBookingView],
) -> CancelResolve:
    if len(candidates) == 1:
        return CancelResolve("one", candidates[0].booking_id, tuple(all_views))
    if not candidates:
        return CancelResolve("not_found", views=tuple(all_views))
    return CancelResolve("ask", views=tuple(candidates))


def _score_view(text: str, view: ActiveBookingView) -> int:
    score = 0
    if master_matches_text(view.master_name, text):
        score += 10
    if _service_matches_text(view.service_name, text):
        score += 8
    if _when_matches_text(view.when_label, text, slot_on=view.slot_on):
        score += 6
    return score


def _tokens_after_cancel(text: str) -> list[str]:
    cleaned = _CANCEL_STRIP_RE.sub("", text.lower()).strip()
    return [w for w in re.findall(r"[а-яёa-z]+", cleaned) if len(w) >= 3]


def _is_generic_cancel_only(text: str) -> bool:
    """«отмени запись» без мастера/даты/времени — не считаем уточнением."""
    low = text.lower().strip()
    cleaned = _CANCEL_STRIP_RE.sub(" ", low)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    generic = {
        "запись", "записи", "записью", "записей",
        "бронь", "брони", "бронью",
        "визит", "визиты", "визита",
        "приём", "прием", "приёма", "приема",
        "окно", "окна", "окошко",
        "мою", "моя", "мои", "моё", "мое", "моей",
        "эту", "это", "эта", "нашу", "наша",
        "на", "в", "к", "ко", "у",
    }
    tokens = cleaned.split()
    if not tokens:
        return True
    return all(t in generic for t in tokens)


def _has_specific_hint(text: str, views: list[ActiveBookingView]) -> bool:
    if _is_generic_cancel_only(text):
        return False
    if _hinted_times_in_text(text):
        return True
    if _hinted_hours_in_text(text):
        return True
    if any(_score_view(text, v) > 0 for v in views):
        return True
    if _tokens_after_cancel(text):
        return True
    low = text.lower()
    return any(w in low for w in _BOOKING_HINT_WORDS)


def should_cancel_existing_booking(
    text: str,
    *,
    was_in_booking_fsm: bool,
    views: list[ActiveBookingView],
) -> bool:
    if not views:
        return False
    from services.complaint_detect import looks_like_change_mind

    if looks_like_change_mind(text) and not was_in_booking_fsm:
        return True
    if not _has_cancel_word(text):
        return False
    if not was_in_booking_fsm:
        return True
    return _has_specific_hint(text, views)


def looks_like_cancel_intent(text: str, *, in_cancel_fsm: bool = False) -> bool:
    """«Нет» на вопрос про услугу — не отмена записи."""
    if in_cancel_fsm:
        return True
    from services.complaint_detect import looks_like_change_mind

    if looks_like_change_mind(text) or looks_like_cancel_all(text):
        return True
    if _has_cancel_word(text):
        return True
    return False


def looks_like_service_booking_escape(text: str, service_names: list[str]) -> bool:
    """«Маникюр» в выборе отмены — скорее новая запись, не отмена."""
    from services.nlu import _best_match

    raw = (text or "").strip()
    if not raw or _has_cancel_word(raw):
        return False
    if _hinted_hours_in_text(raw) or _hinted_times_in_text(raw):
        return False
    if not _best_match(raw, service_names):
        return False
    return len(raw) <= 40


def resolve_cancel_target(text: str, views: list[ActiveBookingView]) -> CancelResolve:
    if not views:
        return CancelResolve("none")

    from services.complaint_detect import looks_like_change_mind

    if looks_like_change_mind(text):
        if len(views) == 1:
            return CancelResolve("one", views[0].booking_id, tuple(views))
        latest = max(views, key=lambda v: v.booking_id)
        return CancelResolve("one", latest.booking_id, tuple(views))

    if looks_like_cancel_all(text):
        if len(views) == 1:
            return CancelResolve("one", views[0].booking_id, tuple(views))
        return CancelResolve("confirm_all", views=tuple(views))

    if len(views) == 1:
        if not _has_specific_hint(text, views):
            return CancelResolve("one", views[0].booking_id, tuple(views))
        hinted = _resolve_hour_and_day_hints(text, views)
        if hinted is not None:
            return _finalize_candidates(hinted, views)
        score = _score_view(text, views[0])
        if score > 0:
            return CancelResolve("one", views[0].booking_id, tuple(views))
        return CancelResolve("not_found", views=tuple(views))

    if not _has_specific_hint(text, views):
        return CancelResolve("ask", views=tuple(views))

    hinted = _resolve_hour_and_day_hints(text, views)
    if hinted is not None:
        return _finalize_candidates(hinted, views)

    scored = [(v, _score_view(text, v)) for v in views]
    matched = [v for v, s in scored if s > 0]
    if len(matched) == 1:
        return CancelResolve("one", matched[0].booking_id, tuple(views))
    if len(matched) == 0:
        return CancelResolve("not_found", views=tuple(views))
    return CancelResolve("ask", views=tuple(matched))


def resolve_cancel_pick(text: str, views: list[ActiveBookingView]) -> CancelResolve:
    """Выбор записи текстом после «Какую отменить?» — без слова «отмени»."""
    if not views:
        return CancelResolve("none")
    if len(views) == 1:
        if _score_view(text, views[0]) > 0:
            return CancelResolve("one", views[0].booking_id, tuple(views))
        return CancelResolve("not_found", views=tuple(views))

    hinted = _resolve_hour_and_day_hints(text, views)
    if hinted is not None:
        return _finalize_candidates(hinted, views)

    scored = [(v, _score_view(text, v)) for v in views]
    matched = [v for v, s in scored if s > 0]
    if len(matched) == 1:
        return CancelResolve("one", matched[0].booking_id, tuple(views))
    if len(matched) == 0:
        return CancelResolve("not_found", views=tuple(views))
    return CancelResolve("ask", views=tuple(matched))
