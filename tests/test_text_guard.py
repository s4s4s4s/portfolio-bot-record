from services.text_guard import sanitize_bot_text


def test_strips_cjk():
    raw = "У нас OPI и 我们的 коллекции."
    out = sanitize_bot_text(raw)
    assert "我们的" not in out
    assert "OPI" in out


def test_empty_fallback():
    assert sanitize_bot_text("") == ""
