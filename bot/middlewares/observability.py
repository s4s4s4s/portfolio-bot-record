"""Логирование каждого update: тип, user, FSM, длительность, ошибки."""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.logging import get_logger

log = get_logger()


def _event_meta(event: TelegramObject) -> dict[str, Any]:
    if isinstance(event, Message):
        return {
            "kind": "message",
            "user_id": event.from_user.id if event.from_user else None,
            "chat_id": event.chat.id,
            "text": (event.text or event.caption or "")[:200],
        }
    if isinstance(event, CallbackQuery):
        return {
            "kind": "callback",
            "user_id": event.from_user.id if event.from_user else None,
            "data": (event.data or "")[:120],
        }
    return {"kind": type(event).__name__}


class ObservabilityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        meta = _event_meta(event)
        state: FSMContext | None = data.get("state")
        fsm_state: str | None = None
        if state is not None:
            try:
                fsm_state = await state.get_state()
            except Exception:
                fsm_state = None

        started = time.perf_counter()
        log.debug(
            "update_in kind={kind} user_id={user_id} fsm={fsm} meta={meta}",
            kind=meta.get("kind"),
            user_id=meta.get("user_id"),
            fsm=fsm_state,
            meta=meta,
        )
        try:
            result = await handler(event, data)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception(
                "update_failed kind={kind} user_id={user_id} fsm={fsm} elapsed_ms={elapsed:.1f}",
                kind=meta.get("kind"),
                user_id=meta.get("user_id"),
                fsm=fsm_state,
                elapsed=elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "update_ok kind={kind} user_id={user_id} fsm={fsm} elapsed_ms={elapsed:.1f}",
            kind=meta.get("kind"),
            user_id=meta.get("user_id"),
            fsm=fsm_state,
            elapsed=elapsed_ms,
        )
        return result
