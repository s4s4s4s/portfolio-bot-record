"""Конфигурация через pydantic-settings.

Любое отсутствие BOT_TOKEN или пустые ADMIN_IDS приводят к понятной
SystemExit(2) с сообщением — без traceback.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` рядом с шаблоном (не от cwd): иначе при `python -m bot.main` из другой
# папки подхватывается чужой корневой .env или файл не находится вовсе.
_TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
_env_path = _TEMPLATE_ROOT / ".env"
_env_file: str | None = str(_env_path) if _env_path.is_file() else None
if _env_file is None:
    _cwd_env = Path.cwd() / ".env"
    if _cwd_env.is_file():
        _env_file = str(_cwd_env)

_settings_config_kwargs: SettingsConfigDict = {
    "env_file_encoding": "utf-8",
    "extra": "ignore",
    "case_sensitive": False,
}
if _env_file is not None:
    _settings_config_kwargs["env_file"] = _env_file


class Settings(BaseSettings):
    """Все ENV-переменные шаблона. См. .env.example."""

    model_config = _settings_config_kwargs

    # ── Telegram ───────────────────────────────────────────────────
    bot_token: str = Field(default="", validation_alias="BOT_TOKEN")
    admin_ids_raw: str = Field(default="", validation_alias="ADMIN_IDS")
    tz: str = Field(default="Europe/Moscow", validation_alias="TZ")

    # ── Database ───────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/booking.db",
        validation_alias="DATABASE_URL",
    )

    # ── AI / NLU ───────────────────────────────────────────────────
    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3-32b", validation_alias="GROQ_MODEL")
    groq_whisper_model: str = Field(default="whisper-large-v3", validation_alias="GROQ_WHISPER_MODEL")
    ollama_model: str = Field(default="qwen2.5:14b", validation_alias="OLLAMA_MODEL")
    enable_nlu: bool = Field(default=True, validation_alias="ENABLE_NLU")
    enable_voice: bool = Field(default=True, validation_alias="ENABLE_VOICE")
    auto_seed_demo: bool = Field(default=True, validation_alias="AUTO_SEED_DEMO")

    # ── Salon persona / FAQ (короткие ответы без галлюцинаций LLM) ───
    salon_brands: str = Field(
        default="OPI, Gelish, Artistic Nail Design",
        validation_alias="SALON_BRANDS",
    )
    pets_allowed: bool = Field(default=False, validation_alias="PETS_ALLOWED")

    # ── Usage limit (anti-abuse) ─────────────────────────────────────
    enable_usage_limit: bool = Field(default=True, validation_alias="ENABLE_USAGE_LIMIT")
    daily_msg_limit: int = Field(default=100, validation_alias="DAILY_MSG_LIMIT", ge=1)
    daily_msg_strikes_before_block: int = Field(
        default=3, validation_alias="DAILY_MSG_STRIKES_BEFORE_BLOCK", ge=1,
    )
    salon_admin_contact: str = Field(default="", validation_alias="SALON_ADMIN_CONTACT")
    salon_recovery_promo: str = Field(default="", validation_alias="SALON_RECOVERY_PROMO")

    # ── FSM Storage ────────────────────────────────────────────────
    fsm_backend: Literal["memory", "redis"] = Field(
        default="memory", validation_alias="FSM_BACKEND",
    )
    redis_url: str = Field(default="", validation_alias="REDIS_URL")

    # ── Scheduler ──────────────────────────────────────────────────
    reminder_offset_24h_min: int = Field(
        default=1440, validation_alias="REMINDER_OFFSET_24H_MIN", ge=1,
    )
    reminder_offset_2h_min: int = Field(
        default=120, validation_alias="REMINDER_OFFSET_2H_MIN", ge=1,
    )
    rolling_hour_local: int = Field(
        default=3, validation_alias="ROLLING_HOUR_LOCAL", ge=0, le=23,
    )

    # ── Logging / observability ────────────────────────────────────
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_json: bool = Field(default=False, validation_alias="LOG_JSON")
    log_dir: str = Field(default="logs", validation_alias="LOG_DIR")
    log_file_enabled: bool = Field(default=True, validation_alias="LOG_FILE_ENABLED")
    log_file_max_mb: int = Field(default=10, validation_alias="LOG_FILE_MAX_MB", ge=1)
    heartbeat_interval_sec: int = Field(
        default=30, validation_alias="HEARTBEAT_INTERVAL_SEC", ge=5,
    )
    watchdog_max_stale_sec: int = Field(
        default=120, validation_alias="WATCHDOG_MAX_STALE_SEC", ge=30,
    )

    @field_validator("log_level")
    @classmethod
    def _normalize_level(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            return "INFO"
        return v

    @property
    def admin_ids(self) -> list[int]:
        """Парсит ADMIN_IDS из CSV в список int. Пустые/нечисленные значения отбрасывает."""
        result: list[int] = []
        for chunk in self.admin_ids_raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                result.append(int(chunk))
            except ValueError:
                continue
        return result

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql+asyncpg://") or self.database_url.startswith("postgresql://")

    def validate_runtime(self) -> None:
        """Жёсткая проверка ENV перед стартом бота. SystemExit если плохо."""
        if not self.bot_token or self.bot_token in {"replace_at_deploy", "REPLACE", ""}:
            sys.exit(
                "[config] BOT_TOKEN не задан или placeholder. "
                f"Файл с настройками: {_TEMPLATE_ROOT / '.env'} "
                "(скопируйте из .env.example и заполните; токен — у @BotFather). "
                "Либо экспортируйте BOT_TOKEN в окружение. exit=2"
            )
        if not self.admin_ids:
            sys.exit(
                "[config] ADMIN_IDS пуст или невалиден. Укажите хотя бы один Telegram user-id "
                f"в {_TEMPLATE_ROOT / '.env'} или в окружении (см. @userinfobot). exit=2"
            )
        if self.fsm_backend == "redis" and not self.redis_url:
            sys.exit(
                "[config] FSM_BACKEND=redis требует REDIS_URL. exit=2"
            )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton-доступ. Тесты могут override через переменные окружения + reload_settings()."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Перечитать .env (полезно в тестах)."""
    global _settings
    _settings = Settings()
    return _settings
