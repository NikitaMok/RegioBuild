"""Кнопки 👍/👎 под ответом с требованиями."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.api_client import send_feedback
from app.bot.keyboards import main_menu_keyboard

router = Router(name="feedback")

THANKS_TEXT = (
    "Спасибо! Рад, что удалось помочь. "
    "Если понадобится сравнить регионы или другой тип объекта — я рядом."
)
APOLOGY_TEXT = (
    "Жаль, что ответ пока не подошёл. Я ещё учусь на реальных нормативах "
    "и постепенно становлюсь точнее. Загляните позже — к тому времени "
    "ответы должны стать полезнее. Спасибо, что отметили!"
)


@router.callback_query(F.data.startswith("feedback:"))
async def handle_feedback(callback: CallbackQuery) -> None:
    _, vote, query_log_id = callback.data.split(":", 2)
    await send_feedback(query_log_id, vote)

    # убираем кнопки, чтобы не голосовали дважды; меню — отдельным сообщением
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        THANKS_TEXT if vote == "up" else APOLOGY_TEXT,
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
