"""Entrypoint бота. Запускает aiogram-Dispatcher + APScheduler.

Graceful shutdown: SIGTERM → scheduler.shutdown → dp.stop_polling →
bot.session.close. Health-check Dockerfile проверяет наличие БД-файла,
сам процесс health-check'а делает SELECT 1.

⚠️  PID lock file: предотвращает двойной запуск одного и того же бота.
Heartbeat: logs/heartbeat.json — для dev/watch_bot.py watchdog.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import cast

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.handlers import build_root_router
from bot.middlewares import DBSessionMiddleware, ObservabilityMiddleware, UsageLimitMiddleware
from core.config import get_settings
from core.logging import configure_logging, get_logger
from db.session import init_db

_LOCK_FILE = Path(__file__).with_suffix(".pid")
_TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
_HEARTBEAT_FILE = _TEMPLATE_ROOT / "logs" / "heartbeat.json"


async def _build_storage() -> MemoryStorage:
    settings = get_settings()
    if settings.fsm_backend == "redis":
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            return cast(MemoryStorage, RedisStorage.from_url(settings.redis_url))
        except ImportError:
            get_logger().warning(
                "fsm_backend=redis, но aiogram-redis не установлен → fallback на MemoryStorage",
            )
    return MemoryStorage()


def _acquire_lock() -> bool:
    """Возвращает True если lock получен, False если другой процесс уже запущен."""
    try:
        if _LOCK_FILE.exists():
            old_pid = int(_LOCK_FILE.read_text(encoding="utf-8").strip())
            # Windows-compatible process check
            try:
                import psutil
                if psutil.pid_exists(old_pid):
                    return False
            except ImportError:
                import subprocess
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {old_pid}", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True,
                )
                if str(old_pid) in result.stdout:
                    return False
        _LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return True  # if we can't check, let it start


def _release_lock() -> None:
    try:
        if _LOCK_FILE.exists() and _LOCK_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            _LOCK_FILE.unlink()
    except Exception:
        pass


async def _heartbeat_loop(interval_sec: int, log) -> None:
    _HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    while True:
        payload = {
            "ts": time.time(),
            "pid": os.getpid(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            _HEARTBEAT_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as exc:
            log.warning("heartbeat_write_failed err={err}", err=exc)
        await asyncio.sleep(interval_sec)


def _register_error_handler(dp: Dispatcher, log) -> None:
    @dp.errors()
    async def _on_error(event: ErrorEvent) -> bool:
        update_id = event.update.update_id if event.update else None
        exc = event.exception
        exc_name = type(exc).__name__ if exc else "Unknown"
        log.exception(
            "dispatcher_error update_id={update_id} exc={exc_name}",
            update_id=update_id,
            exc_name=exc_name,
        )
        if exc_name == "TelegramConflictError":
            log.critical(
                "TelegramConflictError: вероятно запущено несколько экземпляров bot.main "
                "с одним BOT_TOKEN — остановите дубликаты"
            )
        return True


async def main() -> None:
    if not _acquire_lock():
        print("ERROR: Booking bot already running (PID lock). Exiting.", file=sys.stderr)
        sys.exit(1)

    settings = get_settings()
    settings.validate_runtime()
    configure_logging(
        level=settings.log_level,
        json_output=settings.log_json,
        log_dir=settings.log_dir,
        log_file_enabled=settings.log_file_enabled,
        log_file_max_mb=settings.log_file_max_mb,
    )
    log = get_logger()

    log.info("Booking-bot стартует...")
    await init_db()
    if settings.auto_seed_demo:
        from seeders.demo_data import ensure_demo_data_if_empty, migrate_legacy_service_names

        await migrate_legacy_service_names()
        seeded = await ensure_demo_data_if_empty()
        if seeded:
            log.info(
                "AUTO_SEED: demo data loaded (services=%s masters=%s slots=%s)",
                seeded["services"],
                seeded["masters"],
                seeded["slots_created"],
            )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=await _build_storage())
    _register_error_handler(dp, log)
    dp.update.middleware(ObservabilityMiddleware())
    dp.update.middleware(DBSessionMiddleware())
    dp.update.middleware(UsageLimitMiddleware())
    dp.include_router(build_root_router())

    from services.notifier import AiogramNotifier
    from services.scheduler import build_scheduler, register_jobs

    notifier = AiogramNotifier(bot)
    scheduler = build_scheduler()
    register_jobs(scheduler, notifier_factory=notifier)
    scheduler.start()

    stop_event = asyncio.Event()

    def _request_stop(*_: object) -> None:
        log.info("получен SIGTERM/SIGINT, начинаю graceful shutdown")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    polling_task = asyncio.create_task(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))
    heartbeat_task = asyncio.create_task(_heartbeat_loop(settings.heartbeat_interval_sec, log))

    try:
        await stop_event.wait()
    finally:
        log.info("graceful shutdown: останавливаю scheduler + polling")
        scheduler.shutdown(wait=True)
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await dp.stop_polling()
        polling_task.cancel()
        try:
            await polling_task
        except (asyncio.CancelledError, Exception):
            pass
        await bot.session.close()
        _release_lock()
        log.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
