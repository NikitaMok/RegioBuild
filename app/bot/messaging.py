"""Нарезка длинных HTML-ответов под лимит Telegram (~4096)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message

TELEGRAM_SAFE_CHUNK = 3500


def split_html_message(text: str, max_len: int = TELEGRAM_SAFE_CHUNK) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")

    return chunks


async def answer_html_chunks(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    parts = split_html_message(text)
    for index, part in enumerate(parts):
        markup = reply_markup if index == len(parts) - 1 else None
        await message.answer(part, reply_markup=markup)
