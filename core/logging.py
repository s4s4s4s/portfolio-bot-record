"""Настройка loguru.

В проде LOG_JSON=true → структурный JSON для агрегации (Better Stack,
Datadog, Loki). В dev — человекочитаемый формат.

Файл logs/bot.log с ротацией — для post-mortem после «зависания» или падения.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONFIGURED = False


def configure_logging(
    *,
    level: str = "INFO",
    json_output: bool = False,
    log_dir: str = "logs",
    log_file_enabled: bool = True,
    log_file_max_mb: int = 10,
) -> None:
    """Идемпотентная настройка loguru. Безопасно вызывать повторно."""
    global _CONFIGURED
    logger.remove()

    if json_output:
        logger.add(
            sys.stdout,
            level=level,
            serialize=True,
            backtrace=False,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
                "- <level>{message}</level>"
            ),
            backtrace=False,
            diagnose=False,
        )

    if log_file_enabled:
        log_path = Path(log_dir) / "bot.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rotation = f"{max(1, log_file_max_mb)} MB"
        if json_output:
            logger.add(
                log_path,
                level=level,
                serialize=True,
                rotation=rotation,
                retention="14 days",
                backtrace=True,
                diagnose=False,
                enqueue=True,
            )
        else:
            logger.add(
                log_path,
                level=level,
                format=(
                    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                    "{name}:{function}:{line} - {message}"
                ),
                rotation=rotation,
                retention="14 days",
                backtrace=True,
                diagnose=False,
                enqueue=True,
            )

    _CONFIGURED = True


def get_logger() -> logger.__class__:  # type: ignore[name-defined]
    """Точка получения логгера. Если не настроен — настраивается с дефолтами."""
    if not _CONFIGURED:
        configure_logging()
    return logger
