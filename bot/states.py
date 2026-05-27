"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_master = State()
    choosing_date = State()
    choosing_slot = State()
    entering_name = State()
    entering_phone = State()
    confirm = State()


class FeedbackStates(StatesGroup):
    awaiting_complaint_feedback = State()


class CancelStates(StatesGroup):
    pick_booking = State()
    confirm_cancel_all = State()


class RescheduleStates(StatesGroup):
    pick_booking = State()
    choosing_date = State()
    choosing_slot = State()


class AdminStates(StatesGroup):
    add_slot_master = State()
    add_slot_service = State()
    add_slot_date = State()
    add_slot_time = State()
    block_slot_pick = State()
    broadcast_text = State()
    broadcast_confirm = State()
