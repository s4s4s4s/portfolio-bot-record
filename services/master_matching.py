"""Сопоставление имён мастеров с подсказками из текста (уменьшительные, «к диме»)."""
from __future__ import annotations

import re

_MASTER_PREP_RE = re.compile(
    r"(?:\bк\b\s+|\bу\b\s+|\bмастер(?:у|а)?\s+)([а-яёa-z]{2,12})",
    re.IGNORECASE,
)


def master_stem(name: str) -> str:
    return (name or "").strip().split()[0]


def master_matches_hint(master_name: str, hint: str) -> bool:
    stem = master_stem(master_name)
    if len(stem) < 2:
        return False
    s = stem.lower()
    h = hint.lower().strip()
    if not h or len(h) < 3:
        return False

    if s == h or s in h or h in s:
        return True
    if len(s) >= 4 and s[:4] in h:
        return True
    if len(h) >= 3 and h in s:
        return True

    if h.endswith("ия") and s.startswith(h[:-2]):
        return True
    if h.endswith("ию") and s.startswith(h[:-2]):
        return True
    if s.endswith("ий") and len(s) > 3 and s[:-2] in h:
        return True
    if s.endswith("й") and len(s) > 2 and s[:-1] in h:
        return True
    if s.endswith("а") and len(s) > 2 and s[:-1] in h:
        return True

    if s.startswith("дмитр") and re.match(r"^ди[мма-яё]*", h):
        return True
    if s.startswith("анн") and re.match(r"^ан[ньюяе]*", h):
        return True

    return False


def extract_master_hints(text: str) -> list[str]:
    low = text.lower()
    hints: list[str] = []
    for m in _MASTER_PREP_RE.finditer(low):
        hints.append(m.group(1))
    return hints


def find_master_name(hint: str, candidates: list[str]) -> str | None:
    if not hint or not candidates:
        return None
    matches = [c for c in candidates if master_matches_hint(c, hint)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        low = hint.lower()
        for c in matches:
            if c.lower() == low or c.lower().startswith(low):
                return c
        return matches[0]
    return None


def find_master_in_text(text: str, candidates: list[str]) -> str | None:
    if not text or not candidates:
        return None
    low = text.lower()
    for name in candidates:
        if name.lower() in low:
            return name

    for hint in extract_master_hints(text):
        hit = find_master_name(hint, candidates)
        if hit:
            return hit

    for word in re.findall(r"[а-яёa-z]{2,12}", low):
        hit = find_master_name(word, candidates)
        if hit:
            return hit

    return None


def master_matches_text(master_name: str, text: str) -> bool:
    if not master_name or not text:
        return False
    if master_name.lower() in text.lower():
        return True
    for hint in extract_master_hints(text):
        if master_matches_hint(master_name, hint):
            return True
    for word in re.findall(r"[а-яёa-z]{2,12}", text.lower()):
        if master_matches_hint(master_name, word):
            return True
    stem = master_stem(master_name)
    if len(stem) >= 4 and stem.lower()[:4] in text.lower():
        return True
    if stem.endswith("ий") and len(stem) > 3 and stem.lower()[:-2] in text.lower():
        return True
    return False
