"""Распознавание голосовых сообщений Telegram.

Telegram шлёт голос в формате `.ogg` (Opus). Если whisper (Groq) принимает
mp3/wav — конвертируем через ffmpeg перед отправкой. Если ffmpeg не найден
— пробуем прямой ogg (Groq Whisper поддерживает много форматов).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx

from core.config import get_settings
from core.logging import get_logger

log = get_logger()


async def download_voice_file(bot: object, file_id: str, dest: Path) -> None:
    """Скачивает файл через aiogram Bot.get_file + download."""
    import asyncio

    # aiogram Bot.download is async but writes to disk
    file_info = await bot.get_file(file_id)  # type: ignore[attr-defined]
    await bot.download(file=file_info, destination=dest)  # type: ignore[attr-defined]


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _to_wav(src_ogg: Path, dest_wav: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_ogg), "-ar", "16000", "-ac", "1", "-f", "wav", str(dest_wav)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


async def transcribe_file(file_path: Path, *, groq_key: str | None = None) -> str:
    """Отправляет аудио файл в Groq Whisper."""
    key = groq_key or get_settings().groq_api_key or ""
    if not key:
        log.warning("groq_api_key пуст: распознавание голоса недоступно")
        return ""

    # Конвертируем в wav если ffmpeg есть
    wav_path: Path = file_path
    try:
        if file_path.suffix in {".ogg", ".oga"} and _has_ffmpeg():
            with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav = Path(tmp.name)
            _to_wav(file_path, wav)
            wav_path = wav
    except Exception:
        log.exception("ffmpeg convert failed, trying raw file")

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    model = get_settings().groq_whisper_model or "whisper-large-v3"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with wav_path.open("rb") as f:
                r = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (wav_path.name, f, "audio/wav" if wav_path.suffix == ".wav" else "audio/ogg")},
                    data={"model": model, "language": "ru", "response_format": "json"},
                )
            r.raise_for_status()
            data = r.json()
            return str(data.get("text", "")).strip()
    except Exception:
        log.exception("Whisper transcription failed")
        return ""
    finally:
        if wav_path != file_path:
            wav_path.unlink(missing_ok=True)
