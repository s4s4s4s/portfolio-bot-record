"""Smoke: импорты пакета, конфиг загружается."""
from __future__ import annotations


def test_imports_ok() -> None:
    import bot.handlers.admin
    import bot.handlers.booking
    import bot.handlers.my
    import bot.handlers.start
    import bot.main  # noqa: F401
    import db.models
    import db.session  # noqa: F401
    import seeders.demo_data  # noqa: F401
    import services.notifier
    import services.phone
    import services.scheduler
    import services.slot_generator  # noqa: F401


def test_settings_load_with_env() -> None:
    from core.config import reload_settings
    s = reload_settings()
    assert s.bot_token == "test:token"
    assert 111 in s.admin_ids
    assert 222 in s.admin_ids
    assert s.fsm_backend == "memory"
