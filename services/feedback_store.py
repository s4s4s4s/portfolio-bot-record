"""Простое хранение жалоб/фидбека (jsonl)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_FEEDBACK_PATH = Path(__file__).resolve().parents[1] / "data" / "feedback.jsonl"


def save_complaint_feedback(*, tg_user_id: int, text: str) -> None:
    _FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "tg_user_id": tg_user_id,
        "text": text.strip()[:2000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
