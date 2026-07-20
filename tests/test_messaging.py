from __future__ import annotations

from app.bot.messaging import split_html_message


def test_split_html_message_keeps_short_text() -> None:
    assert split_html_message("короткий ответ") == ["короткий ответ"]


def test_split_html_message_breaks_on_newlines() -> None:
    text = ("строка\n" * 800).strip()
    parts = split_html_message(text, max_len=200)
    assert len(parts) > 1
    assert all(len(part) <= 200 for part in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")
