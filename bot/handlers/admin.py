"""Админ-команды: /admin, /today, /tomorrow, /add_slot, /block_slot, /broadcast."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters import IsAdmin
from bot.keyboards.admin import admin_main_menu, confirm_broadcast_kb
from bot.states import AdminStates
from core.config import get_settings
from db.repositories import (
    AdminLogRepo,
    BookingRepo,
    ClientRepo,
    MasterRepo,
    ServiceRepo,
    SlotRepo,
    UserUsageRepo,
)
from services.notifier import AiogramNotifier, broadcast

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ── /admin ────────────────────────────────────────────────────────────


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer("Админ-меню:", reply_markup=admin_main_menu())


# ── /today, /tomorrow ─────────────────────────────────────────────────


@router.message(Command("today"))
async def cmd_today(message: Message, session: AsyncSession) -> None:
    await _send_day_summary(message, session, target=date.today(), label="сегодня")


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message, session: AsyncSession) -> None:
    await _send_day_summary(message, session, target=date.today() + timedelta(days=1), label="завтра")


@router.callback_query(F.data == "admin:today")
async def cb_today(call: CallbackQuery, session: AsyncSession) -> None:
    if isinstance(call.message, Message):
        await _send_day_summary(call.message, session, target=date.today(), label="сегодня")
    await call.answer()


@router.callback_query(F.data == "admin:tomorrow")
async def cb_tomorrow(call: CallbackQuery, session: AsyncSession) -> None:
    if isinstance(call.message, Message):
        await _send_day_summary(
            call.message, session, target=date.today() + timedelta(days=1), label="завтра",
        )
    await call.answer()


async def _send_day_summary(
    message: Message, session: AsyncSession, *, target: date, label: str,
) -> None:
    after = datetime.combine(target, time.min)
    before = after + timedelta(days=1)
    bookings = await BookingRepo(session).list_active_in_range(after=after, before=before)
    if not bookings:
        await message.answer(f"На {label} записей нет.")
        return
    lines = [f"<b>Записи на {label} ({target.strftime('%d.%m')}):</b>"]
    for b in bookings:
        slot = b.slot
        client = b.client
        service = slot.service if slot else None
        master = slot.master if slot else None
        if not (slot and client and service and master):
            continue
        lines.append(
            f"• {slot.start_at.strftime('%H:%M')} — {service.name} · "
            f"мастер {master.name} · {client.full_name} {client.phone}",
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /add_slot (упрощённый сценарий: master_id, service_id, datetime) ──


@router.message(Command("add_slot"))
async def cmd_add_slot(message: Message, state: FSMContext, session: AsyncSession) -> None:
    masters = await MasterRepo(session).list_active()
    if not masters:
        await message.answer("Нет активных мастеров.")
        return
    listing = "\n".join(f"{m.id}. {m.name}" for m in masters)
    await state.set_state(AdminStates.add_slot_master)
    await message.answer(f"Выберите ID мастера:\n{listing}")


@router.message(AdminStates.add_slot_master)
async def msg_add_slot_master(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите числовой ID мастера.")
        return
    master_id = int(message.text.strip())
    master = await MasterRepo(session).get(master_id)
    if master is None or not master.is_active:
        await message.answer("Мастер с таким ID не найден.")
        return
    services = await ServiceRepo(session).list_active()
    listing = "\n".join(f"{s.id}. {s.name} ({s.duration_min} мин)" for s in services)
    await state.update_data(master_id=master_id)
    await state.set_state(AdminStates.add_slot_service)
    await message.answer(f"Выберите ID услуги:\n{listing}")


@router.message(AdminStates.add_slot_service)
async def msg_add_slot_service(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите числовой ID услуги.")
        return
    service_id = int(message.text.strip())
    service = await ServiceRepo(session).get(service_id)
    if service is None:
        await message.answer("Услуга не найдена.")
        return
    await state.update_data(service_id=service_id, duration_min=service.duration_min)
    await state.set_state(AdminStates.add_slot_time)
    await message.answer(
        "Введите дату и время в формате <code>2026-05-10 14:00</code>:",
        parse_mode="HTML",
    )


@router.message(AdminStates.add_slot_time)
async def msg_add_slot_time(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()
    try:
        when = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Неверный формат. Пример: 2026-05-10 14:00")
        return
    data = await state.get_data()
    master_id = int(data["master_id"])
    service_id = int(data["service_id"])
    duration_min = int(data["duration_min"])
    slot_repo = SlotRepo(session)
    existing = await slot_repo.find_by_master_start(master_id, when)
    if existing is not None:
        await message.answer("Слот с таким временем у мастера уже есть.")
        await state.clear()
        return
    slot = await slot_repo.create_available(
        master_id=master_id,
        service_id=service_id,
        start_at=when,
        duration_min=duration_min,
    )
    if message.from_user is not None:
        await AdminLogRepo(session).write(
            admin_tg_id=message.from_user.id,
            action="add_slot",
            payload={"slot_id": slot.id, "when": raw},
        )
    await state.clear()
    await message.answer(f"✅ Слот #{slot.id} создан на {raw}.")


# ── /block_slot ───────────────────────────────────────────────────────


@router.message(Command("block_slot"))
async def cmd_block_slot(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.block_slot_pick)
    await message.answer("Введите ID слота для блокировки:")


@router.message(AdminStates.block_slot_pick)
async def msg_block_slot(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите числовой ID слота.")
        return
    slot_id = int(message.text.strip())
    slot_repo = SlotRepo(session)
    slot = await slot_repo.get(slot_id)
    if slot is None:
        await message.answer("Слот не найден.")
        return
    try:
        await slot_repo.block(slot)
    except ValueError as e:
        await message.answer(f"Не удалось заблокировать: {e}")
        return
    if message.from_user is not None:
        await AdminLogRepo(session).write(
            admin_tg_id=message.from_user.id,
            action="block_slot",
            payload={"slot_id": slot_id},
        )
    await state.clear()
    await message.answer(f"🚫 Слот #{slot_id} заблокирован.")


# ── /unblock, /user_limit ─────────────────────────────────────────────


@router.message(Command("unblock"))
async def cmd_unblock(message: Message, session: AsyncSession) -> None:
    """Разблокировать пользователя: /unblock <telegram_user_id>"""
    if message.from_user is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /unblock <telegram_user_id>")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("Укажите числовой Telegram user id.")
        return

    usage = await UserUsageRepo(session).unblock(tg_id)
    if usage is None:
        await message.answer(f"Пользователь {tg_id} не найден в базе лимитов.")
        return
    await AdminLogRepo(session).write(
        admin_tg_id=message.from_user.id,
        action="unblock_user",
        payload={"tg_user_id": tg_id},
    )
    await message.answer(f"✅ Пользователь {tg_id} разблокирован (strikes сброшены).")


@router.message(Command("user_limit"))
async def cmd_user_limit(message: Message, session: AsyncSession) -> None:
    """Статус лимита: /user_limit <telegram_user_id>"""
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /user_limit <telegram_user_id>")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("Укажите числовой Telegram user id.")
        return

    settings = get_settings()
    usage = await UserUsageRepo(session).get(tg_id)
    if usage is None:
        await message.answer(f"Пользователь {tg_id}: записей лимита нет (ещё не писал боту).")
        return
    await message.answer(
        f"<b>Лимит пользователя {tg_id}</b>\n"
        f"День: {usage.day_key}\n"
        f"Сообщений сегодня: {usage.msg_count} / {settings.daily_msg_limit}\n"
        f"Нарушений (strikes): {usage.strike_count} / {settings.daily_msg_strikes_before_block}\n"
        f"Заблокирован: {'да' if usage.blocked else 'нет'}",
        parse_mode="HTML",
    )


# ── /broadcast ────────────────────────────────────────────────────────


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.broadcast_text)
    await message.answer("Введите текст рассылки:")


@router.message(AdminStates.broadcast_text)
async def msg_broadcast_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 1:
        await message.answer("Текст пустой. Попробуйте ещё раз.")
        return
    await state.update_data(text=text)
    await state.set_state(AdminStates.broadcast_confirm)
    await message.answer(
        f"Будет отправлено всем клиентам.\n\n«{text}»",
        reply_markup=confirm_broadcast_kb(),
    )


@router.callback_query(AdminStates.broadcast_confirm, F.data == "bcast:cancel")
async def cb_broadcast_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_text("Рассылка отменена.", reply_markup=None)
    await call.answer()


@router.callback_query(AdminStates.broadcast_confirm, F.data == "bcast:go")
async def cb_broadcast_go(
    call: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    data = await state.get_data()
    text = str(data.get("text", "")).strip()
    if not text:
        await call.answer("Пустой текст — нечего слать.", show_alert=True)
        return
    recipients = await ClientRepo(session).list_all_ids()
    if not recipients:
        await call.answer("Нет получателей.", show_alert=True)
        await state.clear()
        return
    bot = call.bot
    if bot is None:
        await call.answer()
        return
    notifier = AiogramNotifier(bot)
    ok, fail = await broadcast(notifier, recipients=recipients, text=text)
    if call.from_user is not None:
        await AdminLogRepo(session).write(
            admin_tg_id=call.from_user.id,
            action="broadcast",
            payload={"recipients": len(recipients), "ok": ok, "fail": fail},
        )
    await state.clear()
    if isinstance(call.message, Message):
        await call.message.edit_text(
            f"📣 Рассылка завершена. Доставлено: {ok}, ошибок: {fail}.", reply_markup=None,
        )
    await call.answer()
