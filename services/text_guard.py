"""Пост-обработка текста бота: язык, длина, пробелы."""
from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_BEAUTY_RE = re.compile(r"\bbeauty[\s\-]*салон\w*\b", re.IGNORECASE)
_BEAUTY_WORD_RE = re.compile(r"\bbeauty\b", re.IGNORECASE)
_MAX_LEN = 400


def sanitize_bot_text(text: str, *, fallback: str = "") -> str:
    if not text or not text.strip():
        return fallback
    out = text.strip()
    if _CJK_RE.search(out):
        out = _CJK_RE.sub("", out).strip()
    out = _BEAUTY_RE.sub("салон красоты", out)
    out = _BEAUTY_WORD_RE.sub("салон красоты", out)
    out = re.sub(r" +", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    if len(out) > _MAX_LEN:
        out = out[: _MAX_LEN - 1].rstrip() + "…"
    if not out.strip():
        return fallback
    return out
