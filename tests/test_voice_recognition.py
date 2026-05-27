"""Tests for voice recognition download and transcription."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.voice_recognition import download_voice_file, transcribe_file


@pytest.mark.asyncio
async def test_download_voice_file(tmp_path: Path):
    bot = MagicMock()
    file_info = MagicMock(file_id="f1")
    bot.get_file = AsyncMock(return_value=file_info)
    bot.download = AsyncMock(return_value=None)

    dest = tmp_path / "voice.ogg"
    await download_voice_file(bot, "f1", dest)
    bot.get_file.assert_awaited_with("f1")
    bot.download.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_file_empty_key(monkeypatch, tmp_path: Path):
    """No GROQ_API_KEY → empty string returned."""
    from core.config import reload_settings
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    reload_settings()

    ogg = tmp_path / "x.ogg"
    ogg.write_text("fake")
    result = await transcribe_file(ogg)
    assert result == ""
